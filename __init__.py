import importlib
import logging
import sys
from . import addon_updater_ops

bl_info = {
    "name": "QuickSnap",
    "author": "Julien Heijmans",
    "blender": (2, 93, 0),
    'version': (1, 4, 6),
    "category": "3D View",
    "description": "Quickly snap objects/vertices/curve points",
    "warning": "",
    "doc_url": "https://github.com/JulienHeijmans/quicksnap",
    "releases_url": "https://github.com/JulienHeijmans/quicksnap/releases",
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
    for current_module_name in modulesFullNames.values():
        if current_module_name in sys.modules:
            if hasattr(sys.modules[current_module_name], 'register'):
                if current_module_name == f"{__name__}.addon_updater_ops":
                    sys.modules[current_module_name].register(bl_info)
                else:
                    sys.modules[current_module_name].register()


def unregister():
    for current_module_name in modulesFullNames.values():
        if current_module_name in sys.modules:
            if hasattr(sys.modules[current_module_name], 'unregister'):
                sys.modules[current_module_name].unregister()


logger = logging.getLogger(__name__)
logger.handlers = []
logger.setLevel(logging.NOTSET)
console_handler = logging.StreamHandler()
console_handler.setFormatter(fmt=logging.Formatter('[%(levelname)s] %(asctime)s %(message)s'))
logger.addHandler(console_handler)
