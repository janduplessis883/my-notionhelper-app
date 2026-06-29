from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from loguru import logger
from notionhelper import NotionHelper


DATA_PATH = Path("weather-images")
DEFAULT_WEATHER_DATABASE_ID = "382fdfd6-8a97-8049-b876-000bfd6077f2"


def _ensure_data_path() -> None:
    DATA_PATH.mkdir(exist_ok=True)
    logger.add(DATA_PATH / "weather.log", rotation="5000 KB")


def fetch_london_hourly_forecast() -> pd.DataFrame:
    _ensure_data_path()
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 51.5085,
            "longitude": -0.1257,
            "hourly": [
                "temperature_2m",
                "apparent_temperature",
                "rain",
                "cloud_cover",
                "cloud_cover_low",
                "cloud_cover_mid",
                "cloud_cover_high",
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    forecast = response.json()

    logger.info(f"API Response: {forecast}")
    hourly = forecast["hourly"]

    hourly_dataframe = pd.DataFrame(
        {
            "date": pd.to_datetime(hourly["time"], utc=True),
            "temperature_2m": hourly["temperature_2m"],
            "apparent_temperature": hourly["apparent_temperature"],
            "rain": hourly["rain"],
            "cloud_cover": hourly["cloud_cover"],
        }
    )
    hourly_dataframe.replace([float("inf"), float("-inf")], pd.NA, inplace=True)
    hourly_dataframe.dropna(inplace=True)
    return hourly_dataframe


def create_forecast_charts(hourly_dataframe: pd.DataFrame, timestamp: str) -> tuple[Path, Path]:
    import matplotlib.pyplot as plt
    import seaborn as sns

    temperature_path = DATA_PATH / f"7dayforecast-{timestamp}.png"
    cloud_path = DATA_PATH / f"7dayforcast-cloud-{timestamp}.png"

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.lineplot(data=hourly_dataframe, x="date", y="temperature_2m", color="#d95442", linewidth=4)
    sns.lineplot(data=hourly_dataframe, x="date", y="apparent_temperature", color="#d7d8d7", linewidth=2)
    sns.lineplot(data=hourly_dataframe, x="date", y="rain", color="#50b2d4", linewidth=3)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#888888")
    ax.xaxis.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    plt.title(f"7-Day Forecast London - Temp & Rain - {timestamp}")
    plt.savefig(temperature_path)
    plt.close(fig)
    logger.info("Saved Image File. - TEMP")

    fig, ax = plt.subplots(figsize=(12, 5))
    sns.lineplot(data=hourly_dataframe, x="date", y="cloud_cover", color="#1e293b", linewidth=1)
    plt.fill_between(hourly_dataframe["date"], hourly_dataframe["cloud_cover"], color="#0ea5e9", linewidth=2)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.5, color="#888888")
    ax.xaxis.grid(False)
    plt.title(f"7-Day Forecast London - Cloud Cover - {timestamp}")
    plt.savefig(cloud_path)
    plt.close(fig)
    logger.info("Saved Image File. - CLOUD")

    return temperature_path, cloud_path


def write_blocks(nh: NotionHelper, page_id: str, temperature_path: Path, cloud_path: Path) -> None:
    nh.one_step_image_embed(page_id, str(temperature_path))
    logger.info("Image 1 uploaded to Notion")
    nh.one_step_image_embed(page_id, str(cloud_path))
    logger.info("Image 2 uploaded to Notion")


def run_forecast(notion_token: str, database_id: str = DEFAULT_WEATHER_DATABASE_ID) -> dict:
    current_time = datetime.now()
    timestamp = current_time.strftime("%Y-%m-%d_%H-%M-%S")
    notion_date = current_time.strftime("%Y-%m-%d")

    hourly_dataframe = fetch_london_hourly_forecast()
    temperature_path, cloud_path = create_forecast_charts(hourly_dataframe, timestamp)

    nh = NotionHelper(notion_token)
    output = nh.new_page_to_data_source(
        database_id,
        page_properties={"Date": {"date": {"start": notion_date}}},
    )
    logger.info("Notion Page Created")
    page_id = output["id"]
    write_blocks(nh, page_id, temperature_path, cloud_path)

    return {
        "page_id": page_id,
        "timestamp": timestamp,
        "temperature_path": temperature_path,
        "cloud_path": cloud_path,
        "rows": len(hourly_dataframe),
    }
