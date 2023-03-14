"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
# from difflib import SequenceMatcher
from typing import Optional

# import omni.client


def get_ref_absolute_path_from_relative_path(prim, relative_path) -> Optional[str]:
    return
    # ref_nodes = prim.GetPrimIndex().rootNode.children
    # if ref_nodes:
    #     rel_path = omni.client.normalize_url(relative_path)
    #     winner = (0, None)
    #     for ref_node in ref_nodes:
    #         for layer in ref_node.layerStack.layers:
    #             layer_path = omni.client.normalize_url(str(layer.realPath))
    #             score = SequenceMatcher(None, rel_path, layer_path).ratio()
    #             if score > winner[0]:
    #                 winner = (score, layer_path)
    #     return winner[1]
    # return None
