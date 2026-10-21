# Isi folder `assets/`

Semua berkas di sini gratis & open source, dipakai untuk **deteksi wajah**
(face tracking) saat membuat klip 9:16.

| Berkas | Ukuran | Asal | Lisensi |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | 227 KB | [opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) (model YuNet dari Intel) | Apache-2.0 |
| `haarcascade_frontalface_default.xml` | 930 KB | [opencv/opencv](https://github.com/opencv/opencv) `data/haarcascades/` | Apache-2.0 |
| `test_face_portrait.jpg` | 35 KB | Potret resmi dari White House (domain publik, AS-2022-03) | Public Domain |

`face_detection_yunet_2023mar.onnx` dipakai sebagai detektor utama (lebih akurat
daripada Haar cascade, terutama untuk wajah miring dan wajah kecil). Kalau
berkas ini hilang, program otomatis memakai Haar cascade, dan kalau keduanya
hilang, crop jatuh ke tengah (lihat `problem.md` P-028).

`test_face_portrait.jpg` hanya dipakai `tests/test_face_tracking.py` sebagai
fixture: gambarnya digeser pelan dari kiri ke kanan supaya posisi wajah yang
sebenarnya diketahui dan bisa dibandingkan dengan hasil pelacakan.
