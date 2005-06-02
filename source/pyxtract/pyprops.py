#!/usr/bin/env python
import re, os, os.path, sys, pickle

propbegindef=re.compile(r'\s*class\s+(?P<orange_api>(.+_API)?)\s*(?P<name>\w+)(\s*:\s*public\s+(?P<parent>\w+))?')
oranstuffdef=re.compile(r'\s*__REGISTER(?P<abstract>_ABSTRACT)?_CLASS')
propdef=re.compile(r'\s*(?P<ctype>\w+)\s+(?P<cname>\w+)\s*;\s*//P(?P<flags>\w+)?\s*(\((?P<pnameflag>[>+])(?P<pname>\w+)\s*\))?(?P<pdesc>[^\r\n]*)')
compdef=re.compile(r'\s*(?P<ctype>\w+)\s+(?P<cname>\w+)\s*;\s*//C')
vwrapperdef=re.compile(r'VWRAPPER\((?P<cname>[^)]+)')
wrapperdef=re.compile(r'WRAPPER\((?P<cname>[^)]+)')

propwarndef=re.compile(r'\\\\P')
compwarndef=re.compile(r'\s*__component')

tdidtdef = re.compile('\s*DEFINEDESCENDER\s*\(\s*(?P<name>\w*)')
callbackdef = re.compile('\s*((DEFINE_BUT_OPERATOR)|(DEFINE_CALLBACK))\s*\(\s*(?P<name>\w*)\s*,\s*(?P<parent>\w*)')

listdef = re.compile(r'\s*#define\s*(?P<name>\w+)\s*((_?TOrangeVector)|(TOrangeMap_[KV]*)<)')

notice = \
""" /* This file has been generated by pyprops.py.
       (feel free to edit it and pyprops will feel free to undo your changes). */
"""

def printNQ(str):
  if not quiet:
    print str

def samefiles(n1, n2):
  f1, f2 = open(n1, "rt"), open(n2, "rt")
  same = (f1.readlines()==f2.readlines())
  f1.close()
  f2.close()
  return same

def renew(oldfile, newfile):
    oldexists = os.path.isfile(oldfile)
    if oldexists:
        if not samefiles(oldfile, newfile):
          os.remove(oldfile)
          os.rename(newfile, oldfile)
          printNQ("Renewing " + oldfile)
        else:
          os.remove(newfile)
#          print "Keeping " + pppfile
    else:
        os.rename(newfile, oldfile)
        printNQ("Creating " + oldfile)
        
class ClassDefinition:
    def __init__(self, name, parent, abstract = 0):
        if name == "type":
          print 0
        self.name = name
        self.parent = parent
        self.abstract = abstract
        self.properties = []
        self.components = []
        self.extended = 0
        self.imported = 0


def tf(x):
    return x and "true" or "false"


def storeClass(currentClass, hppfile):
  if currentClass:
    classes[currentClass.name] = currentClass
    files[hppfile] = files.get(hppfile, []) + [currentClass]

normalTypes = ["bool", "int", "float", "string", "TValue"]

noclasswarnings = []

def detectBuiltInProperties(hppfile):
    ff = open(hppfile, "rt")

    istdidt = hppfile=="tdidt.hpp"
    iscallback = hppfile=="callback.hpp"

    currentClass = None
    candidate = candidateBase = ""
    hasapi = 0
    lcount = 0
    for line in ff:
      lcount += 1
      if istdidt:
          found = tdidtdef.match(line)
          if found:
                storeClass(currentClass, hppfile)
                currentClass = ClassDefinition("TTreeDescender_"+found.group("name"), "TTreeDescender")
                continue
      if iscallback:
          found = callbackdef.match(line)
          if found:
                storeClass(currentClass, hppfile)
                currentClass = apply(ClassDefinition, found.group("name", "parent"))
                continue

      found = vwrapperdef.match(line)
      if found:
        vwrappers[hppfile] = vwrappers.get(hppfile, []) + [found.group("cname")]
        continue
        
      found = wrapperdef.match(line)
      if found:
        wrappers[hppfile] = wrappers.get(hppfile, []) + [found.group("cname")]
        continue

      found = propbegindef.match(line)
      if found:
        candidate, candidateBase, hasapi = found.group("name", "parent", "orange_api")
        if candidateBase == "TWrapped":
          candidateBase = None
        elif candidateBase == "TOrangeVector":
          candidateBase = "TOrange"
        continue

      found = oranstuffdef.match(line)
      if found and candidate:
        storeClass(currentClass, hppfile)
        currentClass = ClassDefinition(candidate, candidateBase, found.group("abstract")!=None)
        if not hasapi:
          print "%s(%i): Warning: class '%s' is not exported to DLL" % (hppfile, lcount, candidate)
        continue

      found = propdef.match(line)
      if found:
        if not currentClass:
            print "%s(%i): Warning: property definition out of scope. Ignoring." % (hppfile, lcount)
        else:
            ctype, cname, flags, pnameflag, pname, pdesc = found.group("ctype", "cname", "flags", "pnameflag", "pname", "pdesc")
            normal = ctype in normalTypes
            if not normal and ctype[0]=="P":
              ctype = "T"+ctype[1:]
            if pname:
              if pnameflag=="+":
                pname = (cname, pname)
            else:
              pname = cname
            currentClass.properties.append((ctype, cname, pname, pdesc, flags and ("R" in flags) or 0, flags and ("O" in flags) or 0, normal))
        continue

      found = compdef.match(line)
      if found:
        if not currentClass:
            print "%s(%i): Warning: component definition out of scope. Ignoring." % (hppfile, lcount)
        else:
            ctype, cname = found.group("ctype", "cname")
            if ctype in normalTypes:
              print "%s(%i): Warning: component of non-wrapped type?! Ignoring." % (hppfile, lcount)
            currentClass.components.append(cname)

      found = listdef.match(line)
      if found:
        noclasswarnings.append(found.group("name"))
        continue
      
      found = propwarndef.match(line)
      if found:
        print "%s(%i): Warning: invalid property/component definition." % (hppfile, lcount)
        print "  " + line
        continue
        
    storeClass(currentClass, hppfile)


def writeFile(hppfile, exportf):
    stem = hppfile[:-4]
    newfile = "ppp/%s.ppp.new" % stem
    pppfile = "ppp/%s.ppp" % stem
    
    off = open(newfile, "wt")
    off.write(notice)

    off.write('#include "../%s"\n\n' % hppfile)

# - add parent fields
# - correct property types (P* -> T*)
    extern_classdefs = {}
    for classdef in files[hppfile]:
        tempcd = classes[classdef.parent]
        while tempcd:
            classdef.properties.extend(tempcd.properties)
            classdef.components.extend(tempcd.components)
            if tempcd.extended:
                break
            tempcd = classes[tempcd.parent]
        classdef.extended = 1

    if files[hppfile]:
        exportf.write("\n/* from %s */\n" % hppfile)
    for classdef in files[hppfile]:
        classname = classdef.name

        exportf.write("class EXPORT_DLL %s;\n" % classname)
        
        off.write("\n\n/****** %s *****/\n\n" % classname)

        off.write("TPropertyDescription %s_properties[] = {\n" % classname)
        for ctype, cname, pname, pdesc, ro, ob, builtin in classdef.properties:
            if builtin or (ctype=="TExample"):
                if type(pname)==tuple:
                  off.write('  {"%s", "%s", &typeid(%s), NULL, offsetof(%s, %s), %s, %s},\n' % (pname[0], pdesc, ctype, classname, cname, tf(ro), tf(ob)))
                  off.write('  {"%s", "%s", &typeid(%s), NULL, offsetof(%s, %s), %s, %s},\n' % (pname[1], pdesc, ctype, classname, cname, tf(ro), tf(ob)))
                else:
                  off.write('  {"%s", "%s", &typeid(%s), NULL, offsetof(%s, %s), %s, %s},\n' % (pname, pdesc, ctype, classname, cname, tf(ro), tf(ob)))
            else:
                if not classes.has_key(ctype) and not ctype in noclasswarnings:
                    print "Warning: type %s, required by %s.%s not registered" % (ctype, classname, pname)
                if type(pname)==tuple:
                  off.write('  {"%s", "%s", &typeid(POrange), &%s::st_classDescription, offsetof(%s, %s), %s, %s},\n' % (pname[0], pdesc, ctype, classname, cname, tf(ro), tf(ob)))
                  off.write('  {"%s", "%s", &typeid(POrange), &%s::st_classDescription, offsetof(%s, %s), %s, %s},\n' % (pname[1], pdesc, ctype, classname, cname, tf(ro), tf(ob)))
                else:
                  off.write('  {"%s", "%s", &typeid(POrange), &%s::st_classDescription, offsetof(%s, %s), %s, %s},\n' % (pname, pdesc, ctype, classname, cname, tf(ro), tf(ob)))
        off.write('  {NULL}\n};\n\n')

        off.write("size_t const %s_components[] = { " % classname)
        for ctype, cname, pname, pdesc, ro, ob, builtin in classdef.properties:
            if not builtin:
                off.write('offsetof(%s, %s), ' % (classname, cname))
        for component in classdef.components:
                off.write('offsetof(%s, %s), ' % (classname, component))
        off.write('0};\n')

        if classdef.parent:
            off.write(('TClassDescription %s::st_classDescription = { "%s", &typeid(%s), &%s::st_classDescription, %s_properties, %s_components };\n' +
                       'TClassDescription const *%s::classDescription() const { return &%s::st_classDescription; }\n'
                      ) % (tuple([classname]*3) + (classdef.parent, ) + tuple([classname]*4)))
        else:
            off.write(('TClassDescription %s::st_classDescription = { "%s", &typeid(%s), NULL, %s_properties, %s_components };\n' +
                       'TClassDescription const *%s::classDescription() const { return &%s::st_classDescription; }\n'
                      ) % tuple([classname]*7))
        if not classdef.abstract:
            off.write('TOrange *%s::clone() const { return mlnew %s(*this); }\n' % (classname, classname))

    off.close()
    renew(pppfile, newfile)
##
##    if wrappers.has_key(pppfile):
##      newfile = "ppp/%s.app.new" % stem
##      pppfile = "ppp/%s.app" % stem
##      
##      off = open(newfile, "wt")
##      off.write(notice)
##      
##      off.write("\n#ifdef _MSC_VER\n\n")
##      for c in wrappers[hppfile]:
##          if classes.has_key("T"+c):
##              if classes["T"+c].imported:
##                  off.write("class __cdecl(dllimport) T%s;\nEXPIMP_TEMPLATE template class __cdecl(dllimport) GCPtr<T%s>;\n" % (c, c))
##              else:
##                  off.write("class %(MN)s_API T%(cn)s;\nEXPIMP_TEMPLATE template class %(MN)s_API GCPtr<T%(cn)s>;\n" % {"MN": modulename.upper(), "cn": c})
##              off.write("typedef GCPtr<T%s> P%s;\n\n" % c)
##          else:
##              print "Class T%s, wrapped in file %s, is undefined" % (c, hppfile)
##      off.write("#else\n\n")
##      for c in wrappers[hppfile]:
##          off.write("class T%s; typedef GCPtr<T%s> P%s;\n\n" % (c, c))
##      off.write("#endif\n")
##    off.close()
##    renew(pppfile, newfile)


orig_dir = os.getcwd()

if not os.path.isdir("ppp"):
  os.mkdir("ppp")

files = {}
classes = { None: None}
wrappers = {}
vwrappers = {}
  

args = sys.argv

modulename = ""
i = quite = 0
while(i<len(args)):
  if args[i][0]=="-":
    if args[i][1]=="l":
      i += 1
      f = file(args[i], "rt")
      cs = pickle.load(f)
      for c in cs.values():
        if c:
          c.imported = True
      classes.update(cs)
      f.close()
    elif args[i][1]=="n":
      i += 1
      modulename = args[i].lower()
    elif args[i][1]=="d":
      i += 1
      import os
      os.chdir(args[i])
    elif args[i][1]=="q":
      quiet = 1
  i += 1

if not modulename:
  print "Module name (-n) missing"
  sys.exit()
  
for filename in filter(lambda x: x[-4:]==".hpp", os.listdir(".")):
    detectBuiltInProperties(filename)

exportf = open("ppp/exportdefs.inc", "wt")
for filename in files.keys():
    writeFile(filename, exportf)
exportf.close()

    
f=open("ppp/stamp", "wt")
pickle.dump(classes, f)
f.close()
    
