#!/usr/bin/env bash
# 把 data、logs、docs 存回專案；以遠端最新版為基礎，避免與其他執行衝突
set -u
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
rm -rf /tmp/keep && mkdir -p /tmp/keep
for p in data logs docs; do [ -e "$p" ] && cp -r --parents "$p" /tmp/keep/; done
git fetch -q origin main && git reset -q --hard origin/main
cp -r /tmp/keep/. .
for p in data docs; do [ -e "$p" ] && git add "$p"; done   # logs/ 不提交（可能含敏感訊息）
git commit -q -m "$1 [skip ci]" || { echo "無變更"; exit 0; }
for i in 1 2 3; do git push -q && exit 0; sleep 5; git pull -q --rebase; done
exit 1
