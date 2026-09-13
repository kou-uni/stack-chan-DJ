import asyncio, base64, json, sys, aiohttp

async def main(out, script=None, wait=6.0):
    async with aiohttp.ClientSession() as s:
        async with s.get("http://127.0.0.1:9333/json") as r:
            tabs = await r.json()
        t = [x for x in tabs if x["type"] == "page" and "8779" in x["url"]]
        if not t:
            print("stage のタブがない"); return
        ws_url = t[0]["webSocketDebuggerUrl"]
        async with s.ws_connect(ws_url, max_msg_size=0) as ws:
            i = [0]
            async def call(m, p=None):
                i[0] += 1
                await ws.send_str(json.dumps({"id": i[0], "method": m, "params": p or {}}))
                while True:
                    d = json.loads((await ws.receive()).data)
                    if d.get("id") == i[0]:
                        return d.get("result", {})
            await call("Runtime.enable")
            await asyncio.sleep(wait)
            if script:
                r2 = await call("Runtime.evaluate",
                                {"expression": script, "returnByValue": True})
                print(json.dumps(r2.get("result", {}).get("value"), ensure_ascii=False))
            r3 = await call("Page.captureScreenshot", {"format": "png"})
            open(out, "wb").write(base64.b64decode(r3["data"]))
            print("撮影", out)

asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None,
                 float(sys.argv[3]) if len(sys.argv) > 3 else 6.0))
