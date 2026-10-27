"""Build the TabloView TV app (Google TV, Fire TV) as dist/TabloView-TV.apk, without Android
Studio or Gradle: aapt2, javac, d8, zipalign and apksigner from the Android SDK.

Needs: a JDK 17 (winget install Microsoft.OpenJDK.17) and the Android SDK's command-line tools with
"platforms;android-34" and "build-tools;34.0.0" (sdkmanager), in %LOCALAPPDATA%\\Android\\Sdk or
ANDROID_HOME.

The app is signed with a key kept outside the repo (%USERPROFILE%\\.tabloview\\tv-release.jks, made
on the first build). Keep it: an update signed with a different key won't install over the app.

Usage: python tvapp/build.py
"""
import glob
import os
import secrets
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = "1.1"
VERSION_CODE = 2
MIN_SDK, TARGET_SDK = 21, 34
PACKAGE = "io.github.joedv.tabloview"

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "build"
SDK = Path(os.environ.get("ANDROID_HOME") or Path(os.environ["LOCALAPPDATA"]) / "Android" / "Sdk")
TOOLS = SDK / "build-tools" / "34.0.0"
ANDROID_JAR = SDK / "platforms" / f"android-{TARGET_SDK}" / "android.jar"
KEY_DIR = Path.home() / ".tabloview"
KEYSTORE, KEY_PASS = KEY_DIR / "tv-release.jks", KEY_DIR / "tv-release.pass"


def java_home() -> Path:
    if os.environ.get("JAVA_HOME"):
        return Path(os.environ["JAVA_HOME"])
    found = sorted(glob.glob(r"C:\Program Files\Microsoft\jdk-17*")) + sorted(glob.glob(r"C:\Program Files\Eclipse Adoptium\jdk-17*"))
    if not found:
        sys.exit("No JDK 17 found: winget install Microsoft.OpenJDK.17")
    return Path(found[-1])


def run(*cmd):
    print(">", " ".join(str(c) for c in cmd)[:160])
    subprocess.run([str(c) for c in cmd], check=True)


def tool(name: str) -> Path:
    for ext in (".exe", ".bat", ""):
        p = TOOLS / f"{name}{ext}"
        if p.exists():
            return p
    sys.exit(f"{name} not found in {TOOLS}: install build-tools;34.0.0 with sdkmanager")


def images(res: Path) -> None:
    """The launcher icon (TabloView's own) and the 320x180 banner the TV home screen shows."""
    sys.path.insert(0, str(ROOT))
    from app.icon import draw_icon
    from PIL import Image, ImageDraw, ImageFont
    for folder, size in (("mipmap-mdpi", 48), ("mipmap-hdpi", 72), ("mipmap-xhdpi", 96), ("mipmap-xxhdpi", 144)):
        (res / folder).mkdir(parents=True, exist_ok=True)
        draw_icon(size).save(res / folder / "icon.png")
    banner = Image.new("RGB", (320, 180), (17, 19, 26))
    icon = draw_icon(96)
    banner.paste(icon, (20, 42), icon)
    draw = ImageDraw.Draw(banner)
    path = next((f for f in (r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf") if os.path.exists(f)), None)
    size = 34
    font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
    while path and draw.textlength("TabloView", font=font) > 320 - 132 - 16:  # fit beside the icon
        size -= 1
        font = ImageFont.truetype(path, size)
    draw.text((132, 90), "TabloView", fill=(255, 255, 255), font=font, anchor="lm")
    (res / "drawable-xhdpi").mkdir(parents=True, exist_ok=True)
    banner.save(res / "drawable-xhdpi" / "banner.png")


def keystore(keytool: Path) -> str:
    if KEYSTORE.exists():
        return KEY_PASS.read_text().strip()
    KEY_DIR.mkdir(exist_ok=True)
    password = secrets.token_urlsafe(24)
    run(keytool, "-genkeypair", "-keystore", KEYSTORE, "-alias", "tabloview", "-keyalg", "RSA", "-keysize", "3072",
        "-validity", "36500", "-storepass", password, "-keypass", password, "-dname", "CN=TabloView")
    KEY_PASS.write_text(password)
    print(f"Made the signing key {KEYSTORE}. Back it up: updates must be signed with it.")
    return password


def main():
    jdk = java_home()
    # d8 and apksigner are batch files that run Java themselves
    os.environ["JAVA_HOME"] = str(jdk)
    os.environ["PATH"] = str(jdk / "bin") + os.pathsep + os.environ.get("PATH", "")
    if not ANDROID_JAR.exists():
        sys.exit(f"{ANDROID_JAR} not found: install platforms;android-{TARGET_SDK} with sdkmanager")
    # Files on this machine can pick up the read-only flag, which stops rmtree (as build.ps1 notes)
    def writable_then_retry(func, path, _exc):
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if OUT.exists():
        shutil.rmtree(OUT, onexc=writable_then_retry)
    (OUT / "gen").mkdir(parents=True)
    res = OUT / "res"
    shutil.copytree(HERE / "res", res)
    images(res)

    # Resources and manifest
    run(tool("aapt2"), "compile", "--dir", res, "-o", OUT / "res.zip")
    unsigned = OUT / "app-unsigned.apk"
    run(tool("aapt2"), "link", "-I", ANDROID_JAR, "--manifest", HERE / "AndroidManifest.xml", "-o", unsigned,
        "--java", OUT / "gen", "--min-sdk-version", MIN_SDK, "--target-sdk-version", TARGET_SDK,
        "--version-code", VERSION_CODE, "--version-name", VERSION, OUT / "res.zip")
    build_config = OUT / "gen" / Path(*PACKAGE.split(".")) / "BuildConfig.java"
    build_config.write_text(f"package {PACKAGE};\n\npublic final class BuildConfig {{\n    public static final String VERSION = \"{VERSION}\";\n}}\n")

    # Code
    sources = [str(p) for p in (HERE / "src").rglob("*.java")] + [str(p) for p in (OUT / "gen").rglob("*.java")]
    classes = OUT / "classes"
    run(jdk / "bin" / "javac", "-nowarn", "-source", "8", "-target", "8", "-encoding", "UTF-8",
        "-classpath", ANDROID_JAR, "-d", classes, *sources)
    run(tool("d8"), "--release", "--min-api", MIN_SDK, "--lib", ANDROID_JAR, "--output", OUT,
        *[str(p) for p in classes.rglob("*.class")])
    with zipfile.ZipFile(unsigned, "a") as z:
        z.write(OUT / "classes.dex", "classes.dex")

    # Aligned and signed
    aligned = OUT / "app-aligned.apk"
    run(tool("zipalign"), "-f", "-p", "4", unsigned, aligned)
    password = keystore(jdk / "bin" / "keytool")
    (ROOT / "dist").mkdir(exist_ok=True)
    # One name for every version: each TabloView release attaches it, so
    # .../releases/latest/download/TabloView-TV.apk always gets the newest
    apk = ROOT / "dist" / "TabloView-TV.apk"
    env = {**os.environ, "TABLOVIEW_KEY_PASS": password}
    subprocess.run([str(tool("apksigner")), "sign", "--ks", str(KEYSTORE), "--ks-pass", "env:TABLOVIEW_KEY_PASS",
                    "--out", str(apk), str(aligned)], check=True, env=env)
    print(f"Done: {apk} ({apk.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
