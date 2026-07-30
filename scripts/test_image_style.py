from pathlib import Path
from generate_post import generate_image_prompts
from image_gen import _generate_image_bytes

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "test_output"
TEST_TOPIC = "Sichere Fahrten mit dem behindertengerechten V-Class inkl. Rollstuhl-Hublift"
TEST_CAPTION = "Manchmal ist der Weg zum Auto die groesste Huerde des Tages. Mit unserer barrierefreien V-Klasse und Rollstuhl-Hublift wird die Fahrt zum Arzttermin oder Besuch wieder entspannt - sicher begleitet, ohne Stress."


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    prompts = generate_image_prompts(TEST_TOPIC, TEST_CAPTION)
    for i, prompt in enumerate(prompts, start=1):
        print(f"--- Bildidee {i} ---\n{prompt}\n")
        image_bytes = _generate_image_bytes(prompt)
        out_path = OUTPUT_DIR / f"test_{i}.png"
        out_path.write_bytes(image_bytes)
        print(f"Gespeichert: {out_path}")
    print(f"Fertig: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
