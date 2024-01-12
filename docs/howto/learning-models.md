# Introduction to Model Replacement

<!--- 📺 _[Work In Progress]_ --->
<!--- #4 PORTAL TUTORIAL VIDEO: Introduction to Model Replacement (ingesting a model, replacing a model, ingesting model texture, replacing model texture) --->

In Remix, models are a core part of enhancing your game, and they'll make up most of your work.  This tutorial will focus on the workflow for models, but it shares some similarities with replacing world textures.


## Ingesting a Model

The RTX Remix tool takes assets from a game capture and cleans them up by removing certain elements, such as particular shaders and texture formats.

<!--- # 6 below needs anchor reference --->
1. **File Format**: Ensure your model is in an acceptable format (see the _Format_ Section for more details on what is acceptable) and load it into Remix
2. **Access Ingest Tab**: Go to the Remix window, find the **Ingest** tab on the top right, and select the **Model(s)** from the vertical left tabs
3. **Input Model**: Upload your source model file by clicking on the **Add** button under the **Input File Path** panel.  
4. **Mass Model Ingestion (optional):** After adding your models into the Input File Path panel, click the **Add to Queue** button to perform a massive ingestion.
5. **Set Output Directory**: In the Output Directory box, navigate to the file path where your project folder is located
6. **Choose Output Format**: Decide between a .usd, .usdc, or .usda file format (see the _Formats _section for more details)
7. **Run Ingestion**: Select the Validation tab from the vertical right menu tabs and select **Run** to run the ingestion process.

> ⚠️ Issues with Ingestion will be highlighted in red with corresponding error messages.

> 📝 All Ingested files, even textures & models, will have MetaData files.


## Replacing a Model

1. **Access Stage**: Go to the "Stage" tab on the top right.
2. **Select Asset Replacements**: Choose the "Asset Replacements" tab on the left.
3. **Layers**: In the top left, you'll see layers. Select your desired layer as the edit target.
4. **Choose Mesh**: Pick your mesh for replacement.
5. **Selection Tab**: Look at the "Selection" tab, where you'll find the original model hash and the converted/captured USD.
6. **Add New Reference**: Click "Add New Reference" and navigate to the ingested model.
7. **Adjust Position and Properties**: Modify the positioning, orientation, and scale using "Object Properties" until it matches the original. You can then safely delete the original captured asset and save that layer.


# Ingesting Model Textures


1. **Ingest**: Go to the **Ingest** tab and select "Texture Ingestion."
2. **Add Texture**: Click "add" and upload the texture you want (PNG or DDS).
3. **Assign Texture Channel (Optional)**:  You have the flexibility to assign the texture to one of seven channels: Diffuse, Emissive Mask, Metallic, Normal - OpenGL, Normal - DirectX, Roughness, or Other. Choose "Other" if you prefer a standardized ingestion without changing the name. While this step is optional, it's usually automated for your convenience.
4. **Output Directory**: Set an output directory within your project file structure.
5. **Run Ingestion**: Click "run" to export the texture. The output directory will contain additional files, but you only need the converted DDS for in-game use.


## Replacing a Model Texture

1. **Stage**: Access "Stage" and go to the "Asset Replacements" tab.
2. **Layers**: Choose your layer as the edit target.
3. **Select Mesh**: Pick your mesh.
4. **Material Properties**: Look for "Material Properties" at the bottom. Assign textures, adjust settings, and save the layer.


## Translucency

**Convert to Translucent:** Translucency is handled in the Ingestion process.  If a material has the word “translucent” or “glass” or “trans” in the name, it will be converted automatically into a translucent material. 


## Emissive Elements

**Emissive Textures:** To make parts of a model emit light, go to the "emissive" tab, tick "Enable Emission," and assign the Emissive Mask map texture. Adjust the Emissive Intensity value as needed.


## Animated Models

**Animated Models**: Remix can't keep weight data for bones on a replaced mesh, so for animated models, first replace the model in-engine and run a new capture with the replaced model. Then, assign ingested PBR textures via Remix to preserve animations. Keep in mind that game performance will control animated models instead of Remix.

**Animated Models:** If your game uses GPU-based skeleton animation, you can replace a 3D model with a new one that shares the same skeleton. This new model will automatically inherit the animation from the original model's bone transformations.

Here's how it works:

**Skeleton Data in the USD Capture**: If the 3D model you want to replace includes skeleton data, you can create a replacement model that uses the same skeleton. This replacement will also be animated.

However, there are some important things to keep in mind:

1. **Bone Indices and Weights:** The runtime of the game only reads bone indices and weights for each vertex from replacement models.
2. **Skeleton Changes:** Modeling tools sometimes alter the skeleton during import/export, which can break the mapping. The tool supports remapping back to the original vertices, but you may need to specify the mapping manually.
3. **Limited Skeleton Information:** The game's skeleton sent to the GPU contains information only from the bind pose to the current pose. This means we can't reconstruct the bind pose or hierarchy, making skinning more challenging.
4. **Differing Joint Counts:** The game's skeleton often has fewer joints than the higher-poly replacement. In such cases, you'll need to remap the joints.

While these issues can be addressed with potential tool features, for now, skinned replacements may require expertise to handle. We're working on making this process more user-friendly, but until then, it's best suited for experienced users who are comfortable with these intricacies.


## Anchor Models

**Anchor Models**: In Remix, there's a situation where some parts of the game's 3D objects can't be easily replaced with new, stable models. This problem typically occurs in older games, especially when the game decides not to show certain parts of the game world because the player can't see them. When this happens, it messes with the identification codes (hashes) of these objects, as they move in and out of the player's view.

To fix this issue, you can create a kind of "stand-in" model, or as we like to call them, **Anchor Models**, in the game level. Think of it as an "anchor" that keeps track of where the full model replacement should go. You'll have to do this for every occurrence of the object you want to replace. Ideally, you should modify the game's levels to make this work seamlessly. But if that's not possible, you can also use a unique prop (a game object) as long as it's not used anywhere else in the game. This unique prop serves as the anchor for the new model, making sure it appears correctly even when parts of the world are hidden from view.