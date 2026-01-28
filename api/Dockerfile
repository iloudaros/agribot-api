# Start from an official Python base image
FROM python:3.11-slim

# Set the working directory for the application
WORKDIR /code

# Copy the dependency file to the root of the WORKDIR
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code into a subdirectory named 'app'
# This makes `from app...` imports work correctly
COPY ./app ./app

# Expose the port the API will run on
EXPOSE 80

# Command to run the application using uvicorn ASGI server
# The app location is now 'app.main:app' because it's inside the 'app' module
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
