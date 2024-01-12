# Introduction to Material Replacement

<!--- 📺 _[Work In Progress]_ --->
<!--- #5 PORTAL TUTORIAL VIDEO: Introduction to Material Replacement (ingesting a texture, replacing a texture) --->

In Remix, materials on meshes get a PBR (Physically-Based Rendering) makeover, allowing you to use high-quality and more physically accurate textures in your game. In this tutorial, we'll focus on replacing materials for world geometry. If you want to replace materials on models, check out the Model Replacement section of this guide.


## Ingesting a Texture

1. **Texture Format**: Ensure your textures are in an acceptable format (see the _Format_ Section for more details on what is acceptable) and load it into Remix
2. **Access Ingest Tab**: Go to the Remix window, find the **Ingest** tab on the top right, and select the **Material(s)** from the vertical left tabs
3. **Input Texture**: Upload your source texture file by clicking on the **Add** button under the **Input File Path** panel.  
4. **Mass Material Ingestion (optional):** After adding your materials into the Input File Path panel, click the **Add to Queue** button to perform a massive ingestion.
5. **Texture Channels (Optional):** You have the flexibility to assign the texture to one of seven channels: Diffuse, Emissive Mask, Metallic, Normal - OpenGL, Normal - DirectX, Roughness, or Other. Choose "Other" if you prefer a standardized ingestion without changing the name. While this step is optional, it's usually automated for your convenience.
6. **Set Output Directory**: In the Output Directory box, navigate to the file path where your project folder is located
7. **Run Ingestion**: Select the Validation tab from the vertical right menu tabs and select **Run** to run the ingestion process.

> ⚠️ Issues with Ingestion will be highlighted in red with corresponding error messages.

> 📝 All Ingested files, even textures & models, will have MetaData files.


## Replacing a Texture

1. **Access Stage:** Go to the **Layout** tab on the top right.
2. **Select Asset Replacements:** Choose the "Asset Replacements" tab on the left.
3. **Layers:** In the top left, you'll find layers. Mark your desired layer as the edit target.
4. **Choose Mesh:** Select the mesh you want to modify.
5. **Material Properties:** At the bottom of the tab, find "Material Properties." Each tab helps you configure the captured material, including textures and settings like emissive intensity.
6. **Texture Replacement:** Pick the drop-down menu relevant to your texture type, then use the "browse" GUI to apply the ingested texture.
7. **Save Layer:** After applying the texture, save the layer. Your texture will now be visible in the game.


## Checking Hash Stability

World geometry has unstable hashes in many older games due to culling mechanisms. To check hash stability, follow these steps:

1. **In-Game Debugging:** In-game, press Alt+X, scroll down to the "Debug" tab under "Rendering", and enable "Debug View".
2. **Check Hash Stability:** To make sure that everything is working smoothly, switch to "Geometry Hash" in the debug view. If you notice a model, texture, or a part of the game world changing color in this view, that's a sign that the hash isn't stable. In such cases, you might need to use a workaround, and replacing it might not be an option.


## Animated Textures

Dealing with animated textures requires some extra steps:

1. **Capture Each Frame:** Slow down the game's framerate and capture each frame of the animated texture.
2. **Use Anchor Textures:** Create a series of Anchor or stand-in textures for each animation frame and render them into a test level to capture the hashes.


### Animated Textures using a Sprite Sheet

To bring animations from a sprite sheet into the application, it's a simple process. The user just needs to specify three things: 
1. The number of rows
1. The number of columns
1. The desired frames per second

Once you've set these values, ensure that all your textures are configured to use sprite sheet textures.

A key point to remember is that the spritesheet should be organized from left to right, and from top to bottom, just like the example image presented below:

<!--- ![SpriteSheetExample](data/images/sprite_sheet_example.png) --->
<img src="data/images/sprite_sheet_example.png" alt="drawing" width="400"/>

> ⚠️ Please be aware that there is a feature gap in the MDL. The runtime will treat all textures as spritesheets, whereas the MDL only treats emissive textures as spritesheets.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://docs.google.com/forms/d/1vym6SgptS4QJvp6ZKTN8Mu9yfd5yQc76B3KHIl-n4DQ/prefill) <sub>