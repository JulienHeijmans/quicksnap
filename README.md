# QuickSnap
QuickSnap is a Blender addon to quickly snap objects/vertices/points to object origins/vertices/points, similar to how vertex snap works in Maya/3Dsmax.

Presentation video:

https://user-images.githubusercontent.com/35562774/193322706-ec02d8a9-0bdf-48a9-8454-c88d7cd1a940.mp4

## Features:
* Snap From/To:
  * Vertices
  * Curve Points
  * Object origins
  * Scene cursor
* Snap onto visible and non visible points (Points closer to the camera are prioritized)
* Highlight target vertex edges for better readability



## Installation
1. Download Code > Download Zip to download the addon on your computer

![image](https://user-images.githubusercontent.com/35562774/193323385-b0df72d3-ca22-4ab9-ba60-29ff64eea0a0.png)

2. In Blender, go to your preferences, in the add-on section, then click "Install..." in teh top-right of the window, and pick the downloaded archive.

## Add-On hotkey and settings
* By default, enable the tool by using Ctrl+Shift+V (For Vertex). Watch out if you have multiple keyboards to your windows settings, Ctrl+Shift will cycle the active keyboard.
* Change the tool hotkey from the Add-On settings window
* Discover the other hotkeys in the add-on settings, and tweak your own preferences
![image](https://user-images.githubusercontent.com/35562774/193323310-b7ba6a3b-7b3d-416a-935f-2c5dab5ad898.png)


## Use the tool
* Select the object or the vertices/edges/faces/curve points you want to move
* Enable the tool using the hotkey (Ctrl+Shift+V by default)
* Move the mouse over the point you want to snap FROM
* Click an hold the right mouse button, mouve the mouse over the point you want to snap TO
* Release the mouse

If you want to cancel the operation:
* Press Right Mouse Button or ESC key to cancel the translation

## Important notes:
This tool is not made to use on very high poly objects, and performance might get poor when many really heavy objects are under the mouse.
If performances are pool, Hide objects/collections that you don't want to snap onto might help.

I am saying this but the tool should be efficient enough in most cases.

## Bug Report:
If you encounter a bug, please report it in the Issue section, and I will have a look at it: https://github.com/JulienHeijmans/quicksnap/issues
Do not forget to explain what you where doing and what was in your scene when the issue happened. If you can share the scene, you can also do so.



