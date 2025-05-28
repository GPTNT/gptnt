AsyncPlay = {"communication_style": "parallel"}
SyncPlay = {"communication_style": "sequential"}

ActFramework = {
    "allow_thoughts_output": False,
    "allow_thoughts_in_history": False,
    "allow_outputs_in_history": True,
}

ReActFramework = {
    "allow_thoughts_output": True,
    "allow_thoughts_in_history": True,
    "allow_outputs_in_history": True,
}

ReDActFramework = {
    "allow_thoughts_output": True,
    "allow_thoughts_in_history": False,
    "allow_outputs_in_history": False,
}

DReActFramework = {
    "allow_thoughts_output": True,
    "allow_thoughts_in_history": False,
    "allow_outputs_in_history": True,
}


# E7
_SoloPlayer = {"role": "defuser", "is_playing_alone": True, "include_manual": True}
SoloPlayerAct = {**_SoloPlayer, **ActFramework, **SyncPlay}
SoloPlayerReAct = {**_SoloPlayer, **ReActFramework, **SyncPlay}

# E3
_SoloDefuser = {"role": "defuser", "is_playing_alone": True, "include_manual": False}
SoloDefuserReAct = {**_SoloDefuser, **ReActFramework, **SyncPlay}


# E1/E4
_Expert = {"role": "expert", "is_playing_alone": False, "include_manual": True}
ExpertAct = {**_Expert, **ActFramework, **SyncPlay}
ExpertReAct = {**_Expert, **ReActFramework, **SyncPlay}

_Defuser = {"role": "defuser", "is_playing_alone": False, "include_manual": False}
DefuserAct = {**_Defuser, **ActFramework, **SyncPlay}
DefuserReAct = {**_Defuser, **ReActFramework, **SyncPlay}

# E8 (E1 + async)
ExpertActAsync = {**_Expert, **ActFramework, **AsyncPlay}
ExpertReActAsync = {**_Expert, **ReActFramework, **AsyncPlay}

DefuserActAsync = {**_Defuser, **ActFramework, **AsyncPlay}
DefuserReActAsync = {**_Defuser, **ReActFramework, **AsyncPlay}
