# -*- coding: utf-8 -*-
"""產生「特賣會通知」捷徑（未簽署），由 Mac 端 `shortcuts sign` 簽署"""
import plistlib, uuid

URL = "https://awantw1984dot.github.io/panic-index/status.json"
FILE = "特賣會_last.txt"
U = lambda: str(uuid.uuid4()).upper()
ids = {k: U() for k in ["url", "upd", "getfile", "filetext", "if1", "events", "combine", "summary", "if2", "text", "save"]}

def out(key, name):
    return {"Type": "ActionOutput", "OutputUUID": ids[key], "OutputName": name}

def attach(key, name):
    return {"Value": out(key, name), "WFSerializationType": "WFTextTokenAttachment"}

def token(parts):
    """parts：字串或 (key, name)；組成含變數的文字"""
    s, att = "", {}
    for p in parts:
        if isinstance(p, str):
            s += p
        else:
            att[f"{{{len(s)}, 1}}"] = out(*p); s += "￼"
    return {"Value": {"string": s, "attachmentsByRange": att}, "WFSerializationType": "WFTextTokenString"}

def act(ident, params):
    return {"WFWorkflowActionIdentifier": ident, "WFWorkflowActionParameters": params}

actions = [
    # 1 取得 status.json
    act("is.workflow.actions.downloadurl", {"UUID": ids["url"], "WFURL": URL}),
    # 2 取得 updated
    act("is.workflow.actions.getvalueforkey", {"UUID": ids["upd"], "WFDictionaryKey": "updated",
        "WFGetDictionaryValueType": "Value", "WFInput": attach("url", "URL 的內容")}),
    # 3 讀取上次通知的時間（捷徑資料夾內；找不到不報錯）
    act("is.workflow.actions.documentpicker.open", {"UUID": ids["getfile"], "WFGetFilePath": FILE,
        "WFFileErrorIfNotFound": False, "WFShowFilePicker": False}),
    # 4 檔案轉文字
    act("is.workflow.actions.detect.text", {"UUID": ids["filetext"], "WFInput": attach("getfile", "檔案")}),
    # 5 如果 上次時間 == 這次時間 → 停止
    act("is.workflow.actions.conditional", {"GroupingIdentifier": ids["if1"], "WFControlFlowMode": 0,
        "WFCondition": 4, "WFInput": {"Type": "Variable", "Variable": attach("filetext", "文字")},
        "WFConditionalActionString": token([("upd", "字典值")])}),
    act("is.workflow.actions.exit", {}),
    act("is.workflow.actions.conditional", {"GroupingIdentifier": ids["if1"], "WFControlFlowMode": 2}),
    # 6 取得 events 並以換行合併
    act("is.workflow.actions.getvalueforkey", {"UUID": ids["events"], "WFDictionaryKey": "events",
        "WFGetDictionaryValueType": "Value", "WFInput": attach("url", "URL 的內容")}),
    act("is.workflow.actions.text.combine", {"UUID": ids["combine"], "WFTextSeparator": "New Lines",
        "text": attach("events", "字典值")}),
    act("is.workflow.actions.getvalueforkey", {"UUID": ids["summary"], "WFDictionaryKey": "summary",
        "WFGetDictionaryValueType": "Value", "WFInput": attach("url", "URL 的內容")}),
    # 7 有事件才通知
    act("is.workflow.actions.conditional", {"GroupingIdentifier": ids["if2"], "WFControlFlowMode": 0,
        "WFCondition": 100, "WFInput": {"Type": "Variable", "Variable": attach("combine", "合併的文字")}}),
    act("is.workflow.actions.notification", {"WFNotificationActionTitle": "特賣會儀表板",
        "WFNotificationActionBody": token([("combine", "合併的文字"), "\n", ("summary", "字典值")]),
        "WFNotificationActionSound": True}),
    act("is.workflow.actions.conditional", {"GroupingIdentifier": ids["if2"], "WFControlFlowMode": 2}),
    # 8 記下這次的更新時間
    act("is.workflow.actions.gettext", {"UUID": ids["text"], "WFTextActionText": token([("upd", "字典值")])}),
    act("is.workflow.actions.documentpicker.save", {"UUID": ids["save"], "WFAskWhereToSave": False,
        "WFFileDestinationPath": FILE, "WFSaveFileOverwrite": True, "WFInput": attach("text", "文字")}),
]

wf = {
    "WFWorkflowActions": actions,
    "WFWorkflowClientVersion": "2607.0.2",
    "WFWorkflowMinimumClientVersion": 900,
    "WFWorkflowMinimumClientVersionString": "900",
    "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4282601983, "WFWorkflowIconGlyphNumber": 59511},
    "WFWorkflowImportQuestions": [],
    "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
    "WFWorkflowOutputContentItemClasses": [],
    "WFWorkflowTypes": [],
    "WFWorkflowHasShortcutInputVariables": False,
    "WFQuickActionSurfaces": [],
}
with open("特賣會通知_unsigned.shortcut", "wb") as f:
    plistlib.dump(wf, f, fmt=plistlib.FMT_BINARY)
for i, a in enumerate(actions, 1):
    print(i, a["WFWorkflowActionIdentifier"])
