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

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://docs.google.com/forms/d/1vym6SgptS4QJvp6ZKTN8Mu9yfd5yQc76B3KHIl-n4DQ/prefill) <sub>