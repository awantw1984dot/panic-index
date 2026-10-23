# -*- coding: utf-8 -*-
"""產生「特賣會通知」捷徑（未簽署），由 Mac 端 `shortcuts sign` 簽署"""
import plistlib, uuid

import sys
TEST = "--test" in sys.argv   # 測試版：讀 status_test.json（next_due 設在過去），用來確認「更新延遲」提醒
URL = "https://awantw1984dot.github.io/panic-index/" + ("status_test.json" if TEST else "status.json")
NAME = "特賣會通知（延遲測試）" if TEST else "特賣會通知"
FILE = "特賣會_last.txt"
U = lambda: str(uuid.uuid4()).upper()
ids = {k: U() for k in ["url", "upd", "getfile", "filetext", "if1", "body", "title", "if2", "text", "save",
                        "due", "duenum", "now", "nownum", "if0"]}

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
    # 2b 更新延遲檢查：status.json 的 next_due（下一次排程最晚應完成的時間，yyyyMMddHHmm）
    #    排程沒跑時 status.json 不會變，現在時間超過 next_due 就提醒，然後結束（不走一般通知）
    act("is.workflow.actions.getvalueforkey", {"UUID": ids["due"], "WFDictionaryKey": "next_due",
        "WFGetDictionaryValueType": "Value", "WFInput": attach("url", "URL 的內容")}),
    act("is.workflow.actions.detect.number", {"UUID": ids["duenum"], "WFInput": attach("due", "字典值")}),
    act("is.workflow.actions.format.date", {"UUID": ids["now"], "WFDateFormatStyle": "Custom",
        "WFDateFormat": "yyyyMMddHHmm",
        "WFDate": {"Value": {"string": "￼", "attachmentsByRange": {"{0, 1}": {"Type": "CurrentDate"}}},
                   "WFSerializationType": "WFTextTokenString"}}),
    act("is.workflow.actions.detect.number", {"UUID": ids["nownum"], "WFInput": attach("now", "格式化的日期")}),
    act("is.workflow.actions.conditional", {"GroupingIdentifier": ids["if0"], "WFControlFlowMode": 0,
        "WFCondition": 2, "WFInput": {"Type": "Variable", "Variable": attach("nownum", "數字")},
        "WFNumberValue": attach("duenum", "數字")}),
    act("is.workflow.actions.notification", {"WFNotificationActionTitle": "特賣會儀表板更新延遲",
        "WFNotificationActionBody": token(["最後更新 ", ("upd", "字典值"), "，自動更新可能延遲或失敗，目前分數不是最新"]),
        "WFNotificationActionSound": True}),
    act("is.workflow.actions.exit", {}),
    act("is.workflow.actions.conditional", {"GroupingIdentifier": ids["if0"], "WFControlFlowMode": 2}),
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
    # 6 通知文字由 GitHub 產生（status.json 的 title、body），之後改措辭不必重新簽署
    act("is.workflow.actions.getvalueforkey", {"UUID": ids["body"], "WFDictionaryKey": "body",
        "WFGetDictionaryValueType": "Value", "WFInput": attach("url", "URL 的內容")}),
    act("is.workflow.actions.getvalueforkey", {"UUID": ids["title"], "WFDictionaryKey": "title",
        "WFGetDictionaryValueType": "Value", "WFInput": attach("url", "URL 的內容")}),
    # 7 body 有內容才通知
    act("is.workflow.actions.conditional", {"GroupingIdentifier": ids["if2"], "WFControlFlowMode": 0,
        "WFCondition": 100, "WFInput": {"Type": "Variable", "Variable": attach("body", "字典值")}}),
    act("is.workflow.actions.notification", {"WFNotificationActionTitle": token([("title", "字典值")]),
        "WFNotificationActionBody": token([("body", "字典值")]), "WFNotificationActionSound": True}),
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
import json
with open(f"{NAME}.wflow", "wb") as f:
    plistlib.dump(wf, f, fmt=plistlib.FMT_XML)
with open(f"{NAME}.json", "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
for i, a in enumerate(actions, 1):
    print(i, a["WFWorkflowActionIdentifier"])
