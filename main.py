from fastapi import FastAPI, HTTPException
import ee
import math
from datetime import datetime, timedelta

app = FastAPI()

ee.Initialize(project="agro-shield")

@app.get("/ndvi")
def get_ndvi(lat: float, lon: float, damage_date: str, hectare: float):

    try:
        damage = datetime.strptime(damage_date, "%Y-%m-%d")

        # Prevent future date
        today = datetime.utcnow().date()
        if damage.date() > today:
            damage = datetime.utcnow()

        # 🌾 Convert hectare → radius
        area_m2 = hectare * 10000
        radius = math.sqrt(area_m2 / math.pi)

        field = ee.Geometry.Point([lon, lat]).buffer(radius)

        # Date ranges
        baseline_start = damage - timedelta(days=7)
        baseline_end = damage - timedelta(days=1)

        current_start = damage - timedelta(days=1)
        current_end = damage

        def get_ndvi_image(start, end):
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(field)
                .filterDate(start.strftime("%Y-%m-%d"),
                            end.strftime("%Y-%m-%d"))
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
                .map(lambda img:
                     img.normalizedDifference(["B8", "B4"])
                     .rename("NDVI"))
            )

            if collection.size().getInfo() == 0:
                return None

            return collection.median()
        
        baseline_img = get_ndvi_image(baseline_start, baseline_end)
        current_img = get_ndvi_image(current_start, current_end)

        # print(baseline_img,current_img)


        def extract_ndvi(image):
            if image is None:
                return 0
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=field,
                scale=10,
                maxPixels=1e9
            )
            val = stats.get("NDVI")
            if val is None:
                return 0
            return float(val.getInfo())

        ndvi_before = extract_ndvi(baseline_img)
        ndvi_after = extract_ndvi(current_img)

        drop = 0
        if ndvi_before > 0:
            drop = ((ndvi_before - ndvi_after) / ndvi_before) * 100
        if drop < 0:
            drop = 0

        vis_params = {
            "min": 0,
            "max": 1,
            "palette": ["red", "yellow", "green"]
        }

        before_heatmap = None
        after_heatmap = None

        if baseline_img is not None:
            before_heatmap = baseline_img.visualize(**vis_params).getThumbURL({
                "region": field,
                "dimensions": 512,
                "format": "png"
            })

        if current_img is not None:
            after_heatmap = current_img.visualize(**vis_params).getThumbURL({
                "region": field,
                "dimensions": 512,
                "format": "png"
            })
        # print(ndvi_before,ndvi_after,drop,before_heatmap,after_heatmap)
        return {
            "before": round(ndvi_before, 3),
            "after": round(ndvi_after, 3),
            "dropPercent": round(drop, 2),
            "beforeHeatmapUrl": before_heatmap,
            "afterHeatmapUrl": after_heatmap
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))