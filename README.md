# QuickSnap
QuickSnap is a Blender addon to quickly snap objects/vertices/points to object origins/vertices/points, similar to how vertex snap works in Maya/3Dsmax.

Presentation video:

https://user-images.githubusercontent.com/35562774/195340412-6931d8f0-045d-4c4d-badd-96b94ef7f1cc.mp4

If the video is not playing for you, you can watch it here: https://youtu.be/9cWV0JELM88

## Features:
* Snap From/To:
  * Scene cursor
  * Object origins
  * Vertices and Curve points
  * Edges mid-points
  * Face centers
  
* A pie menu allows you to change the type of point you snap from/to. Use the same hotkey as the one you use ot open the tool to display the menu.

![pie-menu](https://user-images.githubusercontent.com/35562774/196196537-82078f77-70ab-4929-a36a-6aaf6fe3bfde.gif)
  
* Constrain the translation on a single axis or a plane using (Shift+)X,Y,Z hotkeys
* Automatically display wireframe of the mesh you are snapping to and the wireframe of the object right under the mouse (Can be turned off)
* Snap onto visible and non visible points (Points closer to the camera are prioritized)
* Highlight target vertex edges, as well as potential target edge midpoint and target facecenters for better readability
* An Add-On updater allows you to update the addon from within the preference menu



## Installation
1. Click on the green button Code > Download Zip to download the addon on your computer

![image](https://user-images.githubusercontent.com/35562774/193323385-b0df72d3-ca22-4ab9-ba60-29ff64eea0a0.png)

2. In Blender, go to your preferences, in the add-on section, then click "Install..." in teh top-right of the window, and pick the downloaded archive.

## Add-On hotkey and settings
* By default, enable the tool by using Ctrl+Shift+V (For Vertex). Watch out if you have multiple keyboards to your windows settings, Ctrl+Shift will cycle the active keyboard.
* Change the tool hotkey from the Add-On settings window
* Discover the other hotkeys in the add-on settings, and tweak your own preferences
![image](https://user-images.githubusercontent.com/35562774/196199499-a99c0ad4-1d56-4eb2-bd0a-1e6a0e242b20.png)


## Use the tool
* Select the object or the vertices/edges/faces/curve points you want to move
* Enable the tool using the hotkey (Ctrl+Shift+V by default)
* Whith the tool enabled use the same hotkey (Ctrl+Shift+V by default) to open the pie menu and chose what you snap from*to (Vertices and curve points / edge midpoints / face centers)
* Move the mouse over the point you want to snap FROM
* Click an hold the right mouse button, mouve the mouse over the point you want to snap TO
* Release the mouse

If you want to cancel the operation:
* Press Right Mouse Button or ESC key to cancel the translation

## Important notes:
This tool is not made to use on very high poly objects, and performance might get poor when many really heavy objects are under the mouse.
If performances are poor, hiding objects/collections that you don't want to snap onto will help.

I am saying this but the tool should be efficient enough in most cases.


## Update the Add-On
* In the Add-on preferences, scroll down, click on "Check now for QuickSnap update"
* If the same button now says: "Update now to (x,y,z)" it means that a new version exists. Click that button to update, then restart Blender.
* Here is a video showing how ot update the add-on from within blender: (You need to click on the play icon in the top right corner)

![quicksnap-update](https://user-images.githubusercontent.com/35562774/195124862-dd573b55-ee2a-4995-a068-dd568822186d.gif)
  
  
## Bug Report:
* If you have an issue, first check that you have the last version of the addon (instructions above)
* If the problem persist with the latest version of the addon:
  * Please create an issue here, and I will try to fix the issue asap: https://github.com/JulienHeijmans/quicksnap/issues
  * Do not forget to explain what you were doing and what was in your scene when the issue happened. If you can share the scene, you can also do so.

## Known issues / limitation:
* Target highlighting does not work with 'Ignore modifiers' enabled. I plan to investigate new ways to ignore modifiers that might allow highlighting in that situation.
* In edit mode, the tool will always use the original points of the mesh (Without modifiers)
