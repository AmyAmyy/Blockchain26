# Blockchain Engineering Assignments

## Instructions Lab 1

### Setup

```bash
cd Lab1
python -m venv venv
venv\Scripts\activate            # This is for Windows
pip install -r requirements.txt
```

This will create a virtual environment and install all necessary libraries. Also create a `.env` file in `Lab1/` with the following:
```
EMAIL=your_email@example.com
```

### Usage

```bash
python Lab1.py
```

When running the algorithm the first time a private key is generated and stored in `Lab1/my_key.pem`. It is important to store this private key safely.

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
Copy the private key generated that was generated when running `Lab1` and that is stored in the `Lab1/my_key.pem`. Place it in the `Lab3` folder. Also store each members public key in text files called `Lab3/first_key.txt`, `Lab3/second_key.txt` and `Lab3/third_key.txt`.


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

#### For the forking bonus assignment:

If you want to create a partition, set `PARTITION_TEST_ENABLED` to True in `Lab3/constants.py` for the peer that you want separated. After 30 seconds of running the peer will start to ignore messages and will not send messages to other peers. After another 30 seconds it will try to reconnect again.