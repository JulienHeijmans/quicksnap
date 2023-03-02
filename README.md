# QuickSnap
QuickSnap is a Blender addon to quickly snap objects/vertices/points to object origins/vertices/points, similar to how vertex snap works in Maya/3Dsmax.

Presentation video:

https://user-images.githubusercontent.com/35562774/195340412-6931d8f0-045d-4c4d-badd-96b94ef7f1cc.mp4

If the video is not playing for you, you can watch it here: https://youtu.be/9cWV0JELM88

## Update Notes:
Check the [Release Page](https://github.com/JulienHeijmans/quicksnap/releases) to learn about the latest updates.

## Features:
* Snap From/To:
  * Scene cursor
  * Object origins
  * Vertices and Curve points
  * Edges mid-points
  * Face centers
  

    
* New: You can change the snap target type using hotkeys: 1: Vertices/curve points, 2:Edge centers, 3:Face centers, O: Origins
* New: An icon close to the mouse let you know the current snap target type. (You can have it always visible, fade after a few seconds, or completely disabled)

    ![hotkey-icon](https://user-images.githubusercontent.com/35562774/199265091-24b63cdf-780b-4aa1-847c-cfb486469356.gif)
    
* New: The tool can now be used in orthographic view (Triggered by "5" on the numpad), and in local mode (Triggered by "/" on the numpad, isolates the selection)
* New: You can use the tool by clicking once on the target and once on the destination (You can move the camera between the two actions), instead of only by using drag&drop

    ![two-click-workflow](https://user-images.githubusercontent.com/35562774/199266031-7d27c422-83dd-4f15-a051-341dd86d6d93.gif)
    
* New: The tool now works when no object/point is selected. It behaves differently depending if you are in Edit or in Object mode:
  * In Object mode the object under the mouse will be moved to the target position
  
    ![no_selection_object_mode](https://user-images.githubusercontent.com/35562774/199267351-c29a4a40-bf31-4968-87ef-8a1debe4ebc4.gif)
  
  * In edit mode the points under the mouse will be moved, and eventually merged if edit mode auto-merge is enabled.
  
    ![no_selection_edit_mode](https://user-images.githubusercontent.com/35562774/199267808-46811c4c-3b9f-456b-84eb-d603e7aba780.gif)

* A pie menu allows you to change the type of point you snap from/to. Use the same hotkey as the one you use ot open the tool to display the menu.

    ![pie-menu](https://user-images.githubusercontent.com/35562774/196196537-82078f77-70ab-4929-a36a-6aaf6fe3bfde.gif)

* With the option 'Use vertices Auto-Merge in Edit mode' enabled, vertices will merge automatically with vertices at the same location after a snap.

    ![auto-merge](https://user-images.githubusercontent.com/35562774/196421064-38042819-71df-452c-955c-cbf34977f6d9.gif)
    ![image](https://user-images.githubusercontent.com/35562774/196762927-2d5b9616-748a-4b21-8ae9-984503721586.png)

* Constrain the translation on a single axis or a plane using (Shift+)X,Y,Z hotkeys
* Automatically display wireframe of the mesh you are snapping to and the wireframe of the object right under the mouse (Can be turned off)
* Snap onto visible and non visible points (Points closer to the camera are prioritized)
* Highlight target vertex edges, as well as potential target edge midpoint and target facecenters for better readability
    ![target_highlight](https://user-images.githubusercontent.com/35562774/196428455-6ba30a31-faeb-4c7c-9dbc-9b3dcca08af3.gif)
* The addon includes the [Blender Addon Updater](https://github.com/CGCookie/blender-addon-updater) that allows to update the addon easily from within Blender. You will also be notified if a new version has been released. You can enable/disable that behaviour in the addon preferences.

    ![image](https://user-images.githubusercontent.com/35562774/196763149-11ec36c4-5b95-43fe-a3f5-1bfd68f5f3a9.png)


## Installation
1. Click on the green button Code > Download Zip to download the addon on your computer

    ![image](https://user-images.githubusercontent.com/35562774/193323385-b0df72d3-ca22-4ab9-ba60-29ff64eea0a0.png)

2. In Blender, go to your preferences, in the add-on section, then click "Install..." in teh top-right of the window, and pick the downloaded archive.


## Add-On hotkey and settings
* By default, enable the tool by using Ctrl+Shift+V (For Vertex). Watch out if you have multiple keyboards to your windows settings, Ctrl+Shift will cycle the active keyboard.
* Use the same hotkey to display the pie menu
* Change the tool hotkey from the Add-On settings window
* Discover the other hotkeys in the add-on settings, and tweak your own preferences
    ![image](https://user-images.githubusercontent.com/35562774/199269100-9ae643af-ba5f-4ccd-a1f8-354b186f1c7f.png)


## Use the tool
* Select the object or the vertices/edges/faces/curve points you want to move
* Enable the tool using the hotkey (Ctrl+Shift+V by default)
* Select the type of point you want to snap from/to, by either:
  * Usin a hotkey:  1: Vertices/curve points, 2:Edge centers, 3:Face centers, O: Origins
  * Opening the pie menu (by using the same hotkey as the one to enable the tool (Ctrl+Shift+V by default)) and chose what you snap from/to (Vertices and curve points / edge midpoints / face centers)

* To snap you have two options:
  * Click and drag:  
    * Move the mouse over the point you want to snap FROM
    * Click an hold the right mouse button, mouve the mouse over the point you want to snap TO
    * Release the mouse
  * Two-Clicks:
    * Click on the point you want to snap FROM
    * Click on the point you want to snap TO

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

## Version support:
* QuickSnap Latest Version: Blender 2.93 and newer.
