# Use AI Texture Tools

```{seealso}
See the [AI Tool Interface](../toolkitinterface/remix-toolkitinterface-aitools.md) section for more information on the AI Texture Tools in the RTX Remix Toolkit.
```

Elevate the quality of your textures using our AI Texture Tools. Easily upscale low-resolution textures for a 4x improvement, and generate roughness and normal maps to help your assets react properly to path traced light. Ensure that your texture is in one of the accepted formats mentioned in the "DL Texture Formats Accepted" section. For optimal results, start with original textures that are square and have dimensions of 512x512. When using these dimensions, the AI will enhance the texture to a generous 2048x2048 size.

Other dimensions are accepted, however, sticking to these standard resolutions yields the best outcomes. Note that AI-enhancing images larger than 512x512 is feasible, but be cautious, as artifacts may appear, particularly in the normals channel, due to the intricacies of the AI model.

While the [minimum requirements](../remix-overview.md) for running the AI Texture Tools are the same as the RTX Remix Toolkit, it is important to note that the more VRAM you have, the faster your textures will process.  We recommend users have at least 12 GBs of VRAM for a smooth experience.  To upscale a texture, go to the AI Texture tab, enter the path to your texture file, add it to the queue, and it will automatically be run through the AI model.

## Hints

- Closing the project before submitting textures to the AI Texture Tools will speed up the process and ensure enough VRAM is available for the model. See the ["Close Project" button](../toolkitinterface/remix-toolkitinterface-layouttab.md#mod-setup) for more details.
- Third party AI Tools can also be used to enhance textures. See the [REST API](../toolkitinterface/remix-toolkitinterface-restapi.md) section for more details on how the RTX Remix Toolkit REST API can be leveraged to integrate third party tools into your workflow.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
