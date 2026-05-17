# Oracle Fusion Maintenance REST API Project

This project is a Python-based REST API integration project for Oracle Fusion Cloud Maintenance.

The purpose of the project is to automate maintenance-related processes by connecting to Oracle Fusion REST APIs, retrieving maintenance/work-order-related data, and triggering required actions based on the business logic defined in the Python code.

## Project Overview

This project was built as part of an Oracle Fusion Maintenance implementation study.

The main idea is to support a maintenance business case where assets, meters, work orders, and condition-based logic are used to improve maintenance automation and reduce manual work inside Oracle Fusion.

The project connects to Oracle Fusion using REST APIs and executes the logic from the `main.py` file.

## Features

- Connects to Oracle Fusion Cloud REST APIs
- Handles authentication and API requests
- Reads maintenance-related data
- Supports automation logic for maintenance processes
- Runs from a single main Python entry point
- Can be extended for work orders, meters, assets, and condition events

├── requirements.txt
├── .gitignore
└── README.md
