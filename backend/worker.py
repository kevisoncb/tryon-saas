import time
from pathlib import Path

from PIL import Image

from database import SessionLocal
from crud import claim_next_job, set_done, set_error
from image_utils import remove_white_background_fast, detect_torso_box_mediapipe


BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
RESULTS_DIR = STORAGE_DIR / "results"
CUTOUTS_DIR = STORAGE_DIR / "cutouts"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CUTOUTS_DIR.mkdir(parents=True, exist_ok=True)


def overlay_with_pose(person_path: Path, garment_png_path: Path, out_path: Path) -> None:
    person_img = Image.open(person_path).convert("RGBA")
    garment_img = Image.open(garment_png_path).convert("RGBA")

    torso = detect_torso_box_mediapipe(person_path)

    if torso:
        # roupa: largura ~ 1.05x torso, altura proporcional
        target_w = max(1, int(torso.w * 1.05))
        scale = target_w / max(1, garment_img.width)
        target_h = max(1, int(garment_img.height * scale))
        garment_resized = garment_img.resize((target_w, target_h))

        # posição: alinhar topo da roupa próximo do topo do torso
        x = torso.x + (torso.w - garment_resized.width) // 2
        y = torso.y  # topo do tronco
    else:
        # fallback (se pose falhar)
        target_w = max(1, int(person_img.width * 0.60))
        scale = target_w / max(1, garment_img.width)
        target_h = max(1, int(garment_img.height * scale))
        garment_resized = garment_img.resize((target_w, target_h))
        x = (person_img.width - garment_resized.width) // 2
        y = int(person_img.height * 0.22)

    person_img.paste(garment_resized, (x, y), garment_resized)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    person_img.save(out_path, format="PNG")


def main(poll_seconds: float = 1.0) -> None:
    print("Worker iniciado. Aguardando jobs queued... (CTRL+C para sair)")
    while True:
        db = SessionLocal()
        try:
            job = claim_next_job(db)
            if not job:
                time.sleep(poll_seconds)
                continue

            print(f"Processando job {job.id}...")

            try:
                person_path = Path(job.person_image_path)
                garment_path = Path(job.garment_image_path)

                if not person_path.exists():
                    raise FileNotFoundError(f"Person image not found: {person_path}")
                if not garment_path.exists():
                    raise FileNotFoundError(f"Garment image not found: {garment_path}")

                # 1) remover fundo branco (rápido) -> PNG com alpha
                garment_cutout = CUTOUTS_DIR / f"{job.id}_garment_cutout.png"
                remove_white_background_fast(garment_path, garment_cutout)

                # 2) overlay guiado por pose
                result_path = RESULTS_DIR / f"{job.id}.png"
                overlay_with_pose(person_path, garment_cutout, result_path)

                set_done(db, job, str(result_path))
                print(f"Job {job.id} finalizado (done).")

            except Exception as e:
                set_error(db, job, f"{type(e).__name__}: {e}")
                print(f"Job {job.id} erro: {type(e).__name__}: {e}")

        finally:
            db.close()


if __name__ == "__main__":
    main()
