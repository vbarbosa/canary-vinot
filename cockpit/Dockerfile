FROM python:3.12-slim
WORKDIR /srv/cockpit
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pillow==11.*
COPY app ./app
COPY tools ./tools
ENV COCKPIT_DATA_DIR=/srv/canary/data COCKPIT_ICON_DIR=/srv/cockpit/icons
EXPOSE 8090
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
