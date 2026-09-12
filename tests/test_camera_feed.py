"""カメラ映像を流し続ける仕組みの仕様。

## なぜ（2026-09-12、本人の指摘）

> **「今見るって押したら見れる感じか。それはUXが悪いね」**

そのとおり。**押さないと見えない時点で負け。** 開いたらもう映っている。

実測: 1枚 0.40〜0.81秒 / 11KB → **1.9コマ/秒**。動画として成立する。

## 気をつけること

- **実機は1台。** 見る人が2人でも、撮るのは1つの輪。二重に撮らせない
- **誰も見ていないときは撮らない。** 実機が熱を持つし、無駄
- **1枚撮り損ねても止まらない。** 沈黙より、少し古い絵のほうがまし
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dj"))
from panel import CameraFeed   # noqa: E402


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=10))


class Cam:
    def __init__(self, fail_times=0):
        self.shots, self.fail_times = 0, fail_times

    async def __call__(self):
        self.shots += 1
        if self.shots <= self.fail_times:
            raise RuntimeError("撮れなかった")
        await asyncio.sleep(0.01)
        return b"JPEG%d" % self.shots


def test_nobody_watching_means_nothing_is_captured():
    """★誰も見ていないのに撮らない。実機が熱を持つ。"""
    cam = Cam()
    feed = CameraFeed(cam, interval_s=0.02)
    run(asyncio.sleep(0.15))
    assert cam.shots == 0


def test_capture_starts_when_someone_watches_and_stops_after():
    async def go():
        cam = Cam()
        feed = CameraFeed(cam, interval_s=0.02)
        async with feed.viewer():
            await asyncio.sleep(0.15)
            during = cam.shots
        await asyncio.sleep(0.15)
        return during, cam.shots
    during, after = run(go())
    assert during >= 2, f"撮れていない: {during}"
    assert after - during <= 1, "見る人が居なくなっても撮り続けている"


def test_two_viewers_share_one_capture_loop():
    """★実機は1台。人数分撮ってはいけない。"""
    async def go():
        cam = Cam()
        feed = CameraFeed(cam, interval_s=0.02)
        async with feed.viewer(), feed.viewer():
            await asyncio.sleep(0.15)
            return cam.shots
    one = Cam()
    async def solo():
        feed = CameraFeed(one, interval_s=0.02)
        async with feed.viewer():
            await asyncio.sleep(0.15)
            return one.shots
    two_shots, one_shot = run(go()), run(solo())
    assert two_shots <= one_shot + 2, f"二重に撮っている {two_shots} vs {one_shot}"


def test_latest_frame_is_readable():
    async def go():
        cam = Cam()
        feed = CameraFeed(cam, interval_s=0.02)
        async with feed.viewer():
            await asyncio.sleep(0.1)
            return feed.latest
    assert run(go()).startswith(b"JPEG")


def test_a_failed_shot_does_not_stop_the_feed():
    """★1枚撮り損ねても止まらない。**沈黙より、少し古い絵のほうがまし。**"""
    async def go():
        cam = Cam(fail_times=2)
        feed = CameraFeed(cam, interval_s=0.02)
        async with feed.viewer():
            await asyncio.sleep(0.2)
            return feed.latest
    assert run(go()) is not None
