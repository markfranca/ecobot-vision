<p align="center">
<img src="https://raw.githubusercontent.com/wiki/pedropro/TACO/images/logonav.png" width="25%"/>
</p>

TACO is a growing image dataset of waste in the wild. It contains images of litter taken under
diverse environments: woods, roads and beaches. These images are manually labeled and segmented
according to a hierarchical taxonomy to train and evaluate object detection algorithms. Currently,
images are hosted on Flickr and we have a server that is collecting more images and
annotations @ [tacodataset.org](http://tacodataset.org)


<div align="center">
  # ecobot-vision

  Projeto de visão computacional para detecção de lixo com YOLO, webcam e caminho futuro para ESP32-CAM e robô físico.

  ## Estrutura

  - `data/`: anotações COCO e arquivos de origem do dataset
  - `dataset/`: dataset preparado para YOLO (`train/`, `valid/`, `test/`)
  - `scripts/`: download, conversão e split do dataset
  - `src/`: treino e inferência
  - `runs/`: saídas do YOLO, ignoradas pelo Git

  ## Dependências

  ```bash
  pip install -r requirements.txt
  ```

  ## Fluxo recomendado

  1. Baixar ou preparar as imagens.
  2. Converter anotações COCO para labels YOLO.
  3. Separar o dataset em `train`, `valid` e `test`.
  4. Gerar `data.yaml`.
  5. Treinar o modelo e salvar `best.pt`.
  6. Rodar inferência na webcam ou em outra câmera.

  ## Scripts principais

  - `scripts/download_dataset.py`: baixa imagens referenciadas pelo COCO.
  - `scripts/convert_coco_to_yolo.py`: converte anotações COCO para labels YOLO.
  - `scripts/split_dataset.py`: organiza `train/`, `valid/` e `test/`.
  - `src/train.py`: treina o YOLO com o `data.yaml`.
  - `src/detect_webcam.py`: executa o modelo na webcam local.
  - `src/detect_camera.py`: executa o modelo em uma câmera genérica ou stream.

  ## Exemplo de uso

  ```bash
  python scripts/download_dataset.py --annotations data/annotations.json --output-dir data
  python scripts/convert_coco_to_yolo.py --annotations data/annotations.json --images-dir data --output-dir dataset
  python scripts/split_dataset.py --dataset-root dataset
  python src/train.py --data dataset/data.yaml --model yolov8n.pt
  python src/detect_webcam.py --weights runs/detect/train/weights/best.pt
  ```

