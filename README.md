# Sortify

Sortify is a Python-based GUI application for classifying waste into predefined categories.  
It is designed to encourage eco-friendly waste disposal practices and demonstrate basic image processing, GUI design, and database management.

<br>

## Features
- Simple and user-friendly GUI built with **customtkinter**.
- Image-based waste classification using **OpenCV** and **NumPy**.
- SQLite database to store and manage user data.
- Offline executable for easy use without additional setup.

<br>

## System Workflow
- User selects a waste image from their device.  
- Image is analyzed and processed with OpenCV.  
- Application classifies the waste into categories (Recyclable, Organic, Hazardous, Reusable, etc.).  
- Classification results are displayed in the GUI.  
- User information and history are stored locally in an SQLite database.
