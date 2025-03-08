# FAQ
## General Questions

### What is RTX Remix and what sets it apart from other modding tools?

> RTX Remix is a cutting-edge modding platform built on NVIDIA Omniverse. What sets it apart is its ability to capture game scenes, enhance materials using generative AI tools, and efficiently create impressive RTX remasters incorporating  path tracing, DLSS, and Reflex. You can even plug in modern assets that feature physically accurate materials and incredible fidelity, into game engines that originally only supported simple color textures and assets of basic polygonal detail.
>
> Beyond its core capabilities, what makes RTX Remix special is that it offers modders a chance to remaster the graphics of a wide variety of games with the same exact workflow and tool–a rarity in modding. Experts who have mastered traditional modding tools can use them in tandem with RTX Remix to make even more impressive mods.

### Can you explain the role of generative AI Texture Tools in RTX Remix and how they enhance materials automatically?

> RTX Remix offers generative AI Texture Tools to automatically enhance textures from classic games. The AI network has been trained on a wide variety of textures, and can analyze them to identify the material properties they are meant to possess. It will generate roughness and normal maps to simulate realistic materials, and upscale the pixel count of textures by 4X, ensuring that the remastered content not only looks stunning but also retains the essence of the original game.

### How does RTX Remix utilize ray tracing in the creation of remastered content?

> RTX Remix integrates full ray tracing technology (also known as path tracing) to simulate the behavior of light in a virtual environment. This results in highly realistic lighting effects, reflections, and shadows, significantly enhancing the visual appeal of the remastered content. The use of ray tracing in RTX Remix contributes to creating a more immersive and visually captivating gaming experience. It is also easier to remaster and author scenes with full ray tracing as it's easier to relight a game when lights behave realistically.

### What role does DLSS play in RTX Remix, and how does it impact performance?

> NVIDIA DLSS 3 utilizes deep learning algorithms to perform DLSS Frame Generation and DLSS Super Resolution, boosting performance while maintaining high-quality visuals. It is an essential technology to enable full ray tracing, also known as path tracing (the most realistic light simulation available), which is used in state of the art games and blockbuster movies. With DLSS 3, powerful RTX GPUs can render jaw dropping visuals without tradeoffs to smoothness or image quality.

### Can RTX Remix be used with any game, or is it limited to specific titles?

> RTX Remix is designed to support  a wide range of games, though its level of compatibility may vary depending on the complexity of the game’s assets and engine. RTX Remix works best with DirectX 8 and 9 games with fixed function pipelines, such as Call of Duty 2, Hitman 2: Silent Assassin, Garry's Mod, Freedom Fighters, Need for Speed Underground 2, and Vampire: The Masquerade – Bloodlines; head to the community compatibility list on ModDB to see which games are compatible. Download any game’s rtx.conf config file and the RTX Remix runtime version it works with, and you are ready to get going with your mod.
>
> Game compatibility will expand over time, in part as NVIDIA publishes more feature-rich versions of the RTX Remix Runtime (the component that handles how RTX Remix hooks to games). In part, compatibility will also improve thanks to the community; in April, we released the RTX Remix Runtime in open source, making it easy for the community to contribute code that can improve RTX Remix’s functionality with a range of games.
>
> Furthermore, we’ve seen the community do unimaginable things like mod fixed function pipelines into existing games, use wrappers that make games compatible, and even contribute to identifying compatible games for ModDB’s community compatibility list. We encourage the community to keep working with us to push the boundaries of which games RTX Remix works with. For more details on compatibility, check out our section on Compatibility.

### I’ve added a RTX Remix runtime and a RTX.conf file from ModDB next to my game and RTX Remix won’t properly hook to it–any suggestions?

> Many classic games do not use a fixed function pipeline for how they render everything, and therefore may struggle to work with RTX Remix. To better understand compatibility, we encourage modders to read about it within our RTX Remix Text Guide. In some cases, a game may not work because its rendering techniques are too modern or primitive. Alternatively, it may not work because it requires unorthodox steps–for example, a wrapper, a unique file structure that allows the RTX Remix Runtime to hook to the game properly, or a different version of the game.
>
> We recommend modders check ModDB’s community resources, which include a compatibility table, rtx.conf file with the proper config settings for each game, as well as any unique steps users have documented that are required to run a particular game well. These resources will continue to improve as they are updated by the community.

### Can RTX Remix remaster a game with new lighting and textures in a single click?

> RTX Remix is not a “one button” solution to remastering. While producing a mod with full ray tracing in RTX Remix is relatively straightforward, if the game assets are not upgraded to possess physically accurate materials, the mod will not likely look right; the likelihood is many textures will look uniformly shiny or matte.
>
> PBR assets with physically accurate materials react properly to realistic lighting. Glass reflects the world with clear detail, while laminate wood flooring has rough, coarse reflections. And stone, though without visible reflections, is still capable of bouncing light and having an effect on the scene. Without taking advantage of PBR, the modder is not fully taking advantage of full ray tracing.
>
> Generative AI Texture Tools can help you get started with converting legacy textures to physically accurate materials. But the most impressive RTX Remix projects (like Portal With RTX, Portal: Prelude RTX and Half Life 2 RTX: An RTX Remix Project) are chock full of lovingly hand made high quality assets with enormous polygonal counts and realistic materials. The best Blender artists will revel in being able to bring their carefully crafted assets into games without compromising on their visuals.
>
> The most ambitious mods also see modders customize and add new lights to each scene to account for how the game now looks with realistic lighting and shadowing. This relighting step can allow for all the advantages of path traced lights while preserving the look of the original game.
>
> When used alongside traditional modding tools, like Valve’s Hammer Editor, RTX Remix can make mods even more spectacular. Modders can reinvent particle systems and redesign aspects of the game RTX Remix can not interface with– for example the level design, the physics, and in-game AI.

### How does RTX Remix simplify the process of capturing game assets for modders?

> RTX Remix streamlines asset capturing by providing an intuitive interface that allows modders to easily capture a game scene and the game assets, before converting them to OpenUSD. The software simplifies the often complex task of capturing models, textures, and other elements, making it accessible to modders.

### What are some notable examples or success stories of games remastered using RTX Remix?

> RTX Remix has been employed in the remastering of several games, including NVIDIA’s own Portal With RTX, as well as the community made Portal: Prelude RTX and the under development Half-Life 2 RTX: An RTX Remix Project. Each remaster has been visually stunning and immersive. If you would like to see more examples of what RTX Remix can do, we encourage you to check out the RTX Remix Discord.

### How user-friendly is RTX Remix for modders with varying levels of experience?

> RTX Remix is designed for experienced modders. The intuitive interface, coupled with step-by-step guides and tutorials, ensures that modders can navigate and utilize the software effectively, unlocking the potential for creative expression. We recommend modders participate in the RTX Remix Discord community to collaborate and learn from one another.

### How much time can I expect to spend with RTX Remix to make a mod?

> It’s truly up to the modder. Some modders will lean heavily on AI and produce mods that feature full ray tracing and replaced textures, but no modifications to geometry and meshes. Others will spend months crafting the perfect remaster, complete with assets that feature 20, 30, or in the case of Half Life 2 RTX: An RTX Remix Project, sometimes 70 times the polygonal detail of assets in the original game.
>
> RTX Remix is a huge time saver, as it takes the need away to juggle dozens of tools to mod a single game’s visuals. You don’t need to be skilled in reverse engineering games to inject full ray tracing into an RTX Remix mod. And in a fully ray traced game where lighting is simulated realistically, it is much easier to reauthor and relight a game as every light behaves just as you expect.
>
> All of that saved time can be spent on leveling up other aspects of a mod or bringing a mod to market sooner.


### How do I give feedback to NVIDIA about my experience with RTX Remix?
> Please share any feedback with us on our RTX Remix GitHub. Simply, follow the steps below:
>
> 1. Go to this [NVIDIAGameWorks RTX Remix](https://github.com/NVIDIAGameWorks/rtx-remix/issues) page
> 2. Click the green "New Issue" button
> 3. Select the bug template (Runtime, Documentation, Toolkit, Feature Request) and click "Get Started"
> 4. Fill out the template, add as many details as possible, include files and screenshots
> 5. Click the green "Submit new issue"
>
> We will develop RTX Remix with close attention paid to the issues documented there.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
