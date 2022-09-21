bl_info = {
    "name": "QuickSnap",
    "author": "Julien Heijmans",
    "blender": (2, 80, 0),
    'version': (0, 0, 1),
    "category": "3D View",
    "description": "Quickly snap objects/vertices/curve points"
}

import importlib,sys
    
modulesNames = ['quicksnap_utils','quicksnap_snapdata','quicksnap']


modulesFullNames = {}
for currentModuleName in modulesNames:
    modulesFullNames[currentModuleName] = ('{}.{}'.format(__name__, currentModuleName))

for currentModuleFullName in modulesFullNames.values():
    if currentModuleFullName in sys.modules:
        importlib.reload(sys.modules[currentModuleFullName])
    else:
        globals()[currentModuleFullName] = importlib.import_module(currentModuleFullName)
        setattr(globals()[currentModuleFullName], 'modulesNames', modulesFullNames)



def register():
    for currentModuleName in modulesFullNames.values():
        if currentModuleName in sys.modules:
            if hasattr(sys.modules[currentModuleName], 'register'):
                sys.modules[currentModuleName].register()        

def unregister():   
    for currentModuleName in modulesFullNames.values():
        if currentModuleName in sys.modules:
            if hasattr(sys.modules[currentModuleName], 'unregister'):
                sys.modules[currentModuleName].unregister()
                

print(f"init file - {__name__}")