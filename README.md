# Blockchain Engineering Assignments

## Instructions Lab 1

### Setup

```bash
cd Lab1
python -m venv venv
venv\Scripts\activate            # This is for Windows
pip install -r requirements.txt
```

This will create a virtual environment and install all necessary libraries. Also replace the email address and Github URL

### Usage

```bash
python Lab1.py
```

When running the algorithm the first time a private key is generated and stored in `Lab1/my_key.pem`. Keep this private key safe; you'll reuse it in later labs.

## Instructions Lab 2
Copy the private key generated that was generated when running `Lab1` and that is stored in the `Lab1/my_key.pem`. Place it in the `Lab2` folder. Also store each members public key in text files called `Lab2/first_key.txt`, `Lab2/second_key.txt` and `Lab2/third_key.txt`.

### Setup
```bash
cd Lab2
python -m venv venv
venv\Scripts\activate            # This is for Windows
pip install -r requirements.txt
```

### Usage

```bash
python main.py
```

## Instructions Lab 3
Copy the private key you generated in Lab 1 (`Lab1/my_key.pem`) into the `Lab3` folder as `my_key.pem` (or ensure `Lab3/my_key.pem` exists). Place each member's public key into the `Lab3` folder as `first_key.txt`, `second_key.txt`, and `third_key.txt` (these files already exist in the provided Lab3 directory for reference).

### Setup
```bash
cd Lab3
python -m venv venv
venv\Scripts\activate            # This is for Windows
pip install -r requirements.txt
```

### Usage

```bash
python main.py
```