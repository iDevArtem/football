def parse_location_input(text: str) -> dict | None:
    if not text:
        return None
    raw = text.strip()
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) < 2:
        return None

    try:
        if len(parts) == 2:
            lat = float(parts[0])
            lng = float(parts[1])
            return {
                "title": "Футбольное поле",
                "address": "",
                "latitude": lat,
                "longitude": lng,
            }
        elif len(parts) == 3:
            title = parts[0]
            lat = float(parts[1])
            lng = float(parts[2])
            return {
                "title": title,
                "address": "",
                "latitude": lat,
                "longitude": lng,
            }
        else:
            title = parts[0]
            address = parts[1]
            lat = float(parts[2])
            lng = float(parts[3])
            return {
                "title": title,
                "address": address,
                "latitude": lat,
                "longitude": lng,
            }
    except (ValueError, TypeError):
        return None
