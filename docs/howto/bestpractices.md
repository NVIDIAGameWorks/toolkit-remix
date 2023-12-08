# Best Practices


## Folder Structure

RTX Remix automatically organizes the captures you take within a simple folder structure.

```text
rtx-remix
└ captures
│ └ capture_(year)_(month)_(day)_(hour)_(minutes)_(seconds).usd
│ └ gameicon.exe_icon
│ ├ lights
│ ├ materials
│ ├ meshes
│ ├ textures
│ ├ thumbs
└ mods ← Manually Made
└ project ← Manually Made
│ ├ models
│ ├ materials
```

It might be helpful to create a desktop shortcut to this rtx-remix folder and rename that shortcut to your preferred project name.  You will need to create a “mods” folder inside this rtx-remix folder.  You may also want to create a project folder to contain the files you’ll be working on.


## Organizing Your Captures

During a big mod project, you might take lots of captures to capture everything you want to change in the game. To keep things organized, it's a good idea to give these pictures names that make sense, like naming them based on the part of the game they belong to. For example, you can choose to add a "ch1_" in front of the name for captures you took in chapter one.

> ⚠️ If you want to change the name of a capture, it's best to do it before creating a project in RTX Remix. Once a project with the capture is made, trying to change the capture's name will cause the project to fail when loading the capture. You can only rename the capture if it's not being used in any projects. \

## Layers

When you create your mod, a file called mod.usda serves as the main control center for your project. It's like the top-level manager. Now, while you can put all your replacement work in this mod.usda, you can also use multiple USDAs stacked on top of each other to keep things organized.

As your mod grows, that single mod.usda file can become massive, potentially reaching thousands or even tens of thousands of lines. The advantage of using USDAs is that they're in a format that's easy to read (ASCII), so you can edit them outside of Remix. This comes in handy when you need to fix any issues with your assets or when multiple people are collaborating in Remix. So, keeping your USDAs organized is crucial for your own peace of mind in the long run.

Before you dive into making replacements, it's smart to think about the kinds of assets you'll be working with. For example, if you're adding new 3D models and new materials to the game world, it's a good idea to split these replacements into different layers. And if the game you're remastering is extensive, you might even want to organize things on a chapter-by-chapter basis.

Remember, there can be such a thing as too much organization, but breaking down your mod into component layers will make it way easier to keep track of all your changes in the long haul.


## Storing Files (Source + Ingested)

Remember the project folder you made in the "SETTING UP PROJECT" section? That's where all the in-game files belong, and it's connected to the game's rtx-remix mod folder through a special shortcut called a symlink. This symlink acts like a shortcut, but it's also where the folder is supposed to be.

Now, to keep things neat and tidy, both for yourself and for the people who will use your mod, it's a good idea to make extra folders inside this project folder. These new folders should organize assets in a way that matches the layers we talked about earlier.

Here's another important point: for the files to work properly in Remix, they need to go through a process called **Ingest**. It's smart to set up another folder structure next to your main project folders. This new structure will hold your original assets, like .fbx files (3D models) and png textures, organized in a way that matches your main project folders.

Now, keep in mind that these two sets of folders, the ones for your in-game files and the ones for your source assets, will start taking up quite a bit of space on your computer over time. So, it might be a good idea to consider a versioning system, especially if you're working with a team of people. This helps keep everything organized and makes it easier to collaborate.


## Building a Team

Revamping an entire game is a big challenge, so you might think about forming a team to help out. Remix mods focus a lot on art, and even if your mod involves changing how the game works, it's a good idea to set up a structure that allows multiple artists to collaborate efficiently.

You may want to pick one or two people to handle the Remix setup and asset preparation. This helps avoid confusion and keeps everything consistent. Having too many people involved in this part could lead to mistakes and differences in the project files.