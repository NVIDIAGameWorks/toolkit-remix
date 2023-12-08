# Remix Sample Tutorial
## RTX Remix Runtime Workflow
Prerequisite: Remix runtime found in:: remix-toolkit-install-dir\deps\remix_runtime

![RemixTool Tutorial](../data/images/remix_907.png)

1. Copy the contents of this folder somewhere on your local system, and all the following steps should be performed from that location.  This is just so we can always maintain a clean copy of the original installation.  After your directory should look something like this:
2. Copy the contents of the ‘runtime\.trex’ directory, to the ‘sample’ directory.  So after it should look something like the below.  Since RemixSample.exe is a 64-bit application, we only need the contents of the ".trex" directory.  If your application is 32-bit, then the entire "runtime" directory should be used:

![RemixTool Tutorial](../data/images/remix_908.png)

3. Run "RemixSample.exe" and you should see something like this:


![RemixTool Tutorial](../data/images/remix_909.png)

4. From here, treat this application as any other Remix app.  Menus (ALT+X) and capture should work as expected.  So let’s take a capture and enhance this scene.
5. Press ALT+X to bring up the Remix menu and select the "Developer Settings Menu" button as shown below:

![RemixTool Tutorial](../data/images/remix_910.png)

6. From the "Developer Settings Menu" click on the "Enhancements Tab":

![RemixTool Tutorial](../data/images/remix_911.png)

7. From here, we can specify a name for our capture, and hit the "Capture Scene" button when ready.  This will capture the current frame, and write a USD containing all the data to disk.  The progress bar will show how far into the capturing process we are, once it reaches 100% we can begin the toolkit workflow.

![RemixTool Tutorial](../data/images/remix_912.png)


## RTX Remix Tookit Workflow

1. Launch the Remix Toolkit and select the Setup "Project" button from the startup page:

![RemixTool Tutorial](../data/images/remix_913.png)

2. In the "RTX Remix Project Wizard" select the "Create" button (annotated as number 2 below) to start a new project.

![RemixTool Tutorial](../data/images/remix_914.png)

3. When presented with the dialog below, the next steps are to decide on your project file location and to point the toolkit at the "rtx-remix" directory which is produced as a result of performing a capture in the Remix Runtime (step 5 in the Runtime Workflow section).

![RemixTool Tutorial](../data/images/remix_915.png)

4. In the Project File Directory, navigate to the file path where you created your “project” folder. Type your file name and select the USD file type.  USDA is a text readable representation of USD, which can be useful for debugging, but will consume more memory than the USD (binary) variants.

![RemixTool Tutorial](../data/images/remix_916.png)

5. With the project file location and remix directory configured, select the capture we made earlier and hit the "Create" button.

![RemixTool Tutorial](../data/images/remix_917.png)

6. From here the following should be visible on screen, and the remixing can begin:

![RemixTool Tutorial](../data/images/remix_918.png)