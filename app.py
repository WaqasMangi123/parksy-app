# app.py - Complete Parksy API for Free Hosting
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
from datetime import datetime
import os

class ParksyAPI:
    def __init__(self):
        # Get HERE API key from environment variable
        self.api_key = os.getenv('HERE_API_KEY', 'demo_key_for_testing')
        self.base_url = "https://discover.search.hereapi.com/v1/discover"
        self.geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.parking_api_url = "https://parking.api.here.com/parking/v1/find"

    def geocode_location(self, location_query):
        """Convert location query to coordinates"""
        params = {
            'q': location_query,
            'apiKey': self.api_key,
            'limit': 1
        }

        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                position = data['items'][0]['position']
                address = data['items'][0].get('address', {}).get('label', location_query)
                return position['lat'], position['lng'], address
            else:
                return None, None, None
        except Exception as e:
            print(f"Location search error: {e}")
            return None, None, None

    def search_parking_spots(self, lat, lng, radius=1500):
        """Search for parking spots using HERE API"""
        parking_queries = [
            'parking', 'parking garage', 'car park', 'parking lot',
            'garage', 'park', 'parking space', 'public parking'
        ]

        all_spots = []
        seen_titles = set()

        for query in parking_queries:
            params = {
                'at': f"{lat},{lng}",
                'q': query,
                'limit': 12,
                'apiKey': self.api_key
            }

            try:
                response = requests.get(self.base_url, params=params, timeout=8)
                response.raise_for_status()
                data = response.json()
                spots = data.get('items', [])

                for spot in spots:
                    title = spot.get('title', '')
                    title_key = title.lower().strip()
                    if title_key not in seen_titles and title:
                        seen_titles.add(title_key)
                        all_spots.append(spot)

            except Exception as e:
                continue

        return all_spots

    def estimate_availability(self, parking_spot):
        """Estimate availability based on time and location"""
        current_time = datetime.now()
        hour = current_time.hour
        day_of_week = current_time.weekday()

        availability_score = 50

        if day_of_week < 5:  # Weekdays
            if 8 <= hour <= 10:
                availability_score -= 30
            elif 17 <= hour <= 19:
                availability_score -= 25
            elif 11 <= hour <= 16:
                availability_score -= 15
            else:
                availability_score += 15
        else:  # Weekends
            if 10 <= hour <= 14:
                availability_score -= 20
            else:
                availability_score += 10

        availability_score = max(0, min(100, availability_score))

        if availability_score >= 70:
            status = "LIKELY_AVAILABLE"
            message = "Good chance of finding a spot"
        elif availability_score >= 40:
            status = "MAYBE_AVAILABLE"
            message = "Moderate availability expected"
        else:
            status = "LIKELY_BUSY"
            message = "May be difficult to find parking"

        return {
            'status': status,
            'confidence': 'Medium',
            'message': message,
            'availability_score': availability_score,
            'last_updated': datetime.now().strftime("%H:%M")
        }

    def calculate_parking_score(self, parking_spot):
        """Calculate parking score"""
        score = 50

        distance = parking_spot.get('distance', 1000)
        if distance < 100:
            score += 30
        elif distance < 300:
            score += 20
        elif distance < 500:
            score += 15
        elif distance < 800:
            score += 10

        title = parking_spot.get('title', '').lower()
        parking_keywords = ['parking', 'garage', 'park', 'lot', 'space']
        for keyword in parking_keywords:
            if keyword in title:
                score += 15
                break

        categories = parking_spot.get('categories', [])
        for category in categories:
            cat_name = category.get('name', '').lower()
            if 'parking' in cat_name:
                score += 10

        current_hour = datetime.now().hour
        if 9 <= current_hour <= 17:
            score -= 3
        else:
            score += 5

        return max(20, min(100, score))

    def analyze_parking_type(self, parking_spot):
        """Analyze parking type"""
        title = parking_spot.get('title', '').lower()
        categories = [cat.get('name', '').lower() for cat in parking_spot.get('categories', [])]

        if any('garage' in cat for cat in categories) or 'garage' in title:
            return {
                'type': 'Multi-Level Parking Garage',
                'estimated_cost': '$2-5 per hour',
                'typical_time_limit': 'Varies by facility',
                'advantages': ['Weather protection', 'Security', 'Multiple levels'],
                'considerations': ['Height restrictions', 'Entry fees']
            }
        elif any('lot' in cat for cat in categories) or 'lot' in title:
            return {
                'type': 'Parking Lot',
                'estimated_cost': '$1-3 per hour',
                'typical_time_limit': '2-12 hours typical',
                'advantages': ['Easy access', 'Spacious', 'Good for large vehicles'],
                'considerations': ['Weather exposure', 'Time restrictions']
            }
        else:
            return {
                'type': 'Public Parking Area',
                'estimated_cost': '$1.50-4 per hour',
                'typical_time_limit': 'Varies by location',
                'advantages': ['Public access', 'Regulated pricing'],
                'considerations': ['Time restrictions', 'Payment required']
            }

# Flask App Setup
app = Flask(__name__)
CORS(app)
parksy = ParksyAPI()

@app.route('/', methods=['GET'])
def home():
    """API home endpoint"""
    return jsonify({
        "message": "🅿️ Parksy API is running!",
        "version": "1.0",
        "status": "active",
        "endpoints": {
            "search": "/api/search-parking",
            "details": "/api/parking-details",
            "health": "/api/health"
        },
        "documentation": "https://github.com/your-username/parksy-api"
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "api_version": "1.0",
        "here_api_configured": bool(os.getenv('HERE_API_KEY'))
    })

@app.route('/api/search-parking', methods=['POST'])
def search_parking():
    """Main parking search endpoint"""
    try:
        data = request.get_json()

        if not data or 'location' not in data:
            return jsonify({
                "error": "Location is required",
                "status": "error",
                "example": {"location": "Times Square, New York"}
            }), 400

        location = data['location']

        # Check if HERE API key is configured
        if not os.getenv('HERE_API_KEY'):
            return jsonify({
                "error": "HERE API key not configured",
                "status": "error",
                "message": "Please configure HERE_API_KEY environment variable"
            }), 500

        # Geocode location
        lat, lng, full_address = parksy.geocode_location(location)

        if lat is None:
            return jsonify({
                "error": "Location not found",
                "status": "error",
                "suggestion": "Try a more specific address or city name"
            }), 404

        # Search for parking spots
        parking_spots = parksy.search_parking_spots(lat, lng)

        if not parking_spots:
            return jsonify({
                "message": "No parking spots found in this area",
                "status": "success",
                "data": {
                    "location": full_address,
                    "coordinates": {"lat": lat, "lng": lng},
                    "parking_spots": []
                }
            })

        # Process and score parking spots
        processed_spots = []
        for spot in parking_spots:
            score = parksy.calculate_parking_score(spot)
            availability = parksy.estimate_availability(spot)
            parking_analysis = parksy.analyze_parking_type(spot)

            processed_spot = {
                "id": abs(hash(spot.get('title', '') + str(spot.get('position', {})))),
                "title": spot.get('title', 'Parking Area'),
                "address": spot.get('address', {}).get('label', 'Address not available'),
                "distance": spot.get('distance', 0),
                "coordinates": spot.get('position', {}),
                "score": score,
                "availability": availability,
                "parking_type": parking_analysis,
                "categories": [cat.get('name', '') for cat in spot.get('categories', [])]
            }
            processed_spots.append(processed_spot)

        # Sort by score
        processed_spots.sort(key=lambda x: x['score'], reverse=True)

        return jsonify({
            "message": f"Found {len(processed_spots)} parking options",
            "status": "success",
            "data": {
                "location": full_address,
                "coordinates": {"lat": lat, "lng": lng},
                "search_timestamp": datetime.now().isoformat(),
                "parking_spots": processed_spots
            }
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error",
            "timestamp": datetime.now().isoformat()
        }), 500

@app.route('/api/parking-details', methods=['POST'])
def parking_details():
    """Get detailed information about a specific parking spot"""
    try:
        data = request.get_json()

        if not data or 'spot_id' not in data:
            return jsonify({
                "error": "Spot ID is required",
                "status": "error"
            }), 400

        return jsonify({
            "message": "Detailed parking information",
            "status": "success",
            "data": {
                "spot_id": data['spot_id'],
                "detailed_rules": [
                    "Payment required during business hours",
                    "Maximum 4-hour parking limit",
                    "Valid parking ticket must be displayed",
                    "No overnight parking without permit"
                ],
                "amenities": ["Security cameras", "Lighting", "Easy access"],
                "payment_methods": ["Cash", "Card", "Mobile app"],
                "operating_hours": "24/7",
                "last_updated": datetime.now().isoformat()
            }
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

# For production deployment
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


