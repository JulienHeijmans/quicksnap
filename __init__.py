import importlib
import logging
import sys
from . import addon_updater_ops

bl_info = {
    "name": "QuickSnap",
    "author": "Julien Heijmans",
    "blender": (2, 80, 0),
    'version': (0, 1, 1),
    "category": "3D View",
    "description": "Quickly snap objects/vertices/curve points",
    "warning": "",
    "wiki_url": "https://github.com/JulienHeijmans/quicksnap",
    "tracker_url": "https://github.com/JulienHeijmans/quicksnap/issues",
}


modulesNames = ['addon_updater', 'addon_updater_ops', 'quicksnap_utils', 'quicksnap_snapdata', 'quicksnap_render',
                'quicksnap']

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
    print(f"Register - bl_info=")
    print(bl_info)
    # addon_updater_ops.register(bl_info)
    for current_module_name in modulesFullNames.values():
        if current_module_name in sys.modules:
            if hasattr(sys.modules[current_module_name], 'register'):
                if current_module_name == f"QuickSnap.addon_updater_ops":
                    sys.modules[current_module_name].register(bl_info)
                else:
                    print(f"module name={current_module_name}")
                    sys.modules[current_module_name].register()


def unregister():
    for current_module_name in modulesFullNames.values():
        if current_module_name in sys.modules:
            if hasattr(sys.modules[current_module_name], 'unregister'):
                sys.modules[current_module_name].unregister()


logger = logging.getLogger(__name__)
logger.handlers = []
# logger.setLevel(logging.DEBUG)
logger.setLevel(logging.NOTSET)
console_handler = logging.StreamHandler()
console_handler.setFormatter(fmt=logging.Formatter('[%(levelname)s] %(asctime)s %(message)s'))
logger.addHandler(console_handler)
