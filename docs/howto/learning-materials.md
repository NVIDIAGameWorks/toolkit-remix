# Introduction to Material Replacement

In Remix, materials on meshes get a PBR (Physically-Based Rendering) makeover, allowing you to use high-quality and more physically accurate Materials in your game. In this tutorial, we'll focus on replacing materials for world geometry. If you want to replace materials on models, check out the Model Replacement section of this guide.


## Ingesting a Material

1. **Check File Format:** Ensure your Material is in an acceptable format (refer to the [Format Section](../remix-formats.md) for details) and load the Material into Remix.
2. **Access the Ingest Tab:** Open the Remix window and locate the **Ingest** tab on the top right.  Choose the Material(s) from the vertical left tabs.
3. **Upload Source Material:** Click the **Add** button under the **Input File Path** panel then upload your source Material file.
4. **Set Output Directory:** Paste a folder link into the output directory bar or browse to the directory using the folder icon.
5. **Specify Material Format:** Choose the desired Material format (USD, USDA, or USDC).
6. **Add to Queue:** Press the "Add to Queue" button to initiate the cleanup process.
7. **Post-Ingestion Validation:** After the ingestion process, navigate to the validation tab then access a detailed report on your Material ingestion.

> ⚠️ Issues with Ingestion will be highlighted in red with corresponding error messages.

> 📝 All Ingested files, even Materials & Assets, will have MetaData files.

## Replacing, Adding, or Appending a Material

**Replacing a Material**
This involves substituting an existing Material with a new one.

**Adding a Material**
Adding a Material typically refers to incorporating a new Material alongside existing ones.

**Appending a Material**
 Appending a Material implies sequentially adding Materials to a project. For example, you might start with a basic scene and then append additional Materials to enhance or expand the environment.


1. **Access Stage**: Go to the "Stage" tab on the top right.
2. **Select Material Replacements**: Choose the "Material Replacements" tab on the left.
3. **Layers**: In the top left, you'll see layers. Select your desired layer as the edit target.
4. **Choose Mesh**: Pick your mesh for replacement.
5. **Selection Tab**: Look at the "Selection" tab, where you'll find the original Material hash and the converted/captured USD.
6. **Add New Reference**: Click “Add New Reference” and navigate to the ingested Material to append the new reference.
7. **Adjust Position and Properties**: Modify the positioning, orientation, and scale using "Object Properties" until it matches the original. You can then safely delete the original captured Material and save that layer.


## Checking Hash Stability

World geometry has unstable hashes in many older games due to culling mechanisms. To check hash stability, follow these steps:

1. **In-Game Debugging:** In-game, press Alt+X, scroll down to the "Debug" tab under "Rendering", and enable "Debug View".
2. **Check Hash Stability:** To make sure that everything is working smoothly, switch to "Geometry Hash" in the debug view. If you notice a model, Material, or a part of the game world changing color in this view, that's a sign that the hash isn't stable. In such cases, you might need to use a workaround, and replacing it might not be an option.


## Animated Materials

Working with animated textures involves a few additional steps. Follow this easy guide:

1. **Capture Each Frame:** Slow down the game's framerate to capture each frame of the animated texture.
2. **Use Anchor Textures:**
    * Generate a series of Anchor or stand-in textures for each animation frame.
    * Render these textures into a test level to capture the hashes.
3. **Utilize the Alt+X Developer Menu:**
    * Access the material setup tab in the Alt+X developer menu.
    * Tick on "preserve discarded textures" to retain all the hashes for each frame in the material menu.
4. **Create a Hash List:** Make a list of all the hashes obtained from the preserved frames in the material menu.
5. **Manual Replacement in USDA:** Replace these hashes through simple manual editing in a layer's USDA.

### Animated Materials using a Sprite Sheet

To bring animations from a sprite sheet into the application, it's a simple process. The user just needs to specify three things: 
1. The number of rows
1. The number of columns
1. The desired frames per second

Once you've set these values, ensure that all your Materials are configured to use sprite sheet Materials.

A key point to remember is that the spritesheet should be organized from left to right, and from top to bottom, just like the example image presented below:

<!--- ![SpriteSheetExample](data/images/sprite_sheet_example.png) --->
<img src="../data/images/sprite_sheet_example.png" alt="drawing" width="400"/>


***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) <sub>