import bottle
import argparse
import os
from os import path
import yaml
import shutil


def load_locales(lang_dir):
    locales = {}
    for ent in os.listdir(lang_dir):
        if not ent.endswith(".yml"):
            continue
        lang = path.splitext(ent)[0]
        with open(path.join(lang_dir, ent), mode="r", encoding="utf-8") as f:
            locales[lang] = yaml.load(f.read(), Loader=yaml.FullLoader)

    return locales


def merge_locale(default_locale, locale):
    t = default_locale.copy()
    t.update(locale)
    return t


def render(template_file, lang, locale):
    with open(template_file, mode="r", encoding="utf-8") as f:
        return bottle.template(f.read(), lang=lang, **locale)


def main():
    SELF_DIR = path.dirname(__file__)
    TEMPLETE_FILE = path.join(SELF_DIR, "templates", "index.html.tpl")
    LANG_DIR = path.join(SELF_DIR, "locales")
    ASSET_DIR = path.join(SELF_DIR, "assets")
    OUTPUT_DIR = path.join(SELF_DIR, "..", "public_html")
    DONT_MAKE_CHANGE = ("This file was automatically generated by webgen/gen.py. "
                        "Do not make changes to this file manually.")

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", "-o", type=str, default=OUTPUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    locales = load_locales(LANG_DIR)
    default_lang = "en"
    locale_en = locales[default_lang]
    locale_en["dont_make_change"] = DONT_MAKE_CHANGE
    for lang, locale in locales.items():
        locale = merge_locale(locale_en, locale)
        output_path = path.join(
            args.output_dir,
            "index.html" if lang == default_lang else f"index.{lang}.html")
        with open(output_path, mode="w", encoding="utf-8") as f:
            f.write(render(TEMPLETE_FILE, lang, locale))
    for ent in os.listdir(ASSET_DIR):
        src = path.join(ASSET_DIR, ent)
        dest = path.join(args.output_dir, ent)
        if path.isfile(src):
            shutil.copyfile(src, dest)


if __name__ == "__main__":
    main()
