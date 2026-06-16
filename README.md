# ecobot-vision

Projeto de visao computacional para deteccao de lixo com YOLO, webcam e
ESP32-CAM.

O dataset base vem do TACO, um conjunto de imagens de residuos em ambientes como
ruas, matas e praias.

## Estrutura

- `data/`: anotacoes COCO e arquivos de origem do dataset
- `dataset/`: dataset preparado para YOLO (`train/`, `valid/`, `test`)
- `scripts/`: download, conversao e split do dataset
- `src/`: treino e inferencia
- `runs/`: saidas do YOLO, ignoradas pelo Git

## Dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Fluxo recomendado

1. Baixar ou preparar as imagens.
2. Converter anotacoes COCO para labels YOLO.
3. Separar o dataset em `train`, `valid` e `test`.
4. Gerar `data.yaml`.
5. Treinar o modelo e salvar `best.pt`.
6. Rodar inferencia na webcam ou na ESP32-CAM.

## Treinar

```powershell
python src\train.py --data dataset\data.yaml --model yolov8n.pt
```

## Webcam local

Com pesos treinados:

```powershell
python src\detect_webcam.py --weights runs\trash-detector\weights\best.pt
```

Com YOLO pre-treinado:

```powershell
python src\detect_webcam.py --weights yolov8n.pt
```

## ESP32-CAM

Use o endpoint MJPEG do firmware CameraWebServer:

```powershell
python src\detect_camera.py --source http://IP_DO_ESP32/stream --framesize qvga --weights yolov8n.pt --imgsz 320 --conf 0.35
```

Para usar seu modelo treinado:

```powershell
python src\detect_camera.py --source http://IP_DO_ESP32/stream --framesize qvga --weights runs\trash-detector\weights\best.pt --imgsz 320 --conf 0.25
```

O `detect_camera.py` reconhece automaticamente URLs no formato
`http://IP_DO_ESP32/stream` e usa um leitor MJPEG de baixa latencia com buffer
de 1 frame e reconexao automatica. Tambem e possivel forcar esse modo com
`--esp32`.

Presets aceitos em `--framesize`:

```text
qqvga, qvga, vga, svga, xga, sxga, uxga
```

Voce tambem pode passar o valor numerico diretamente, por exemplo `--framesize 8`.

## Scripts principais

- `scripts/download_dataset.py`: baixa imagens referenciadas pelo COCO.
- `scripts/convert_coco_to_yolo.py`: converte anotacoes COCO para labels YOLO.
- `scripts/split_dataset.py`: organiza `train/`, `valid` e `test`.
- `src/train.py`: treina o YOLO com o `data.yaml`.
- `src/detect_webcam.py`: executa o modelo na webcam local.
- `src/detect_camera.py`: executa o modelo em camera generica, stream ou ESP32-CAM.
