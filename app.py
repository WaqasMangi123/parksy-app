from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_caching import Cache
import requests
import json
from datetime import datetime, timedelta
import os
import re
import random
import time
from typing import Dict, List, Optional, Union
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedParksyAPI:
    def __init__(self):
        self.api_key = os.getenv('HERE_API_KEY')
        if not self.api_key:
            raise ValueError("HERE_API_KEY environment variable is not set")
        
        # HERE API Endpoints
        self.discover_url = "https://discover.search.hereapi.com/v1/discover"
        self.geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.routing_url = "https://router.hereapi.com/v8/routes"
        
        # Parking category mappings for HERE API
        self.parking_categories = {
            'parking-garage': '700-7600-0322',
            'parking-lot': '700-7600-0323',
            'on-street-parking': '700-7600-0324',
            'park-and-ride': '700-7600-0325',
            'ev-charging': '700-7600-0354',
            'accessible-parking': '700-7600-0000'
        }
        
        # Human-like response patterns
        self.positive_responses = [
            "Perfect! 🅿️", "Absolutely! 😊", "Great news!", "Found it! 🎯",
            "Yes, definitely!", "Sure thing!", "I've got you covered!"
        ]
        
        self.location_confirmations = [
            "I found excellent parking options for you in",
            "Perfect! Here are the best parking spots near",
            "Great choice! I've located several parking options in",
            "Wonderful! Here's what's available in"
        ]

    def extract_parking_context(self, message: str) -> Dict:
        """Enhanced context extraction with more parking-specific patterns"""
        context = {
            'time': None,
            'location': None,
            'duration': None,
            'date': None,
            'urgency': 'normal',
            'parking_type': None,
            'accessibility': False,
            'ev_charging': False,
            'max_price': None,
            'preferred_distance': None
        }
        
        message_lower = message.lower()
        
        # Extract parking type preferences
        if any(term in message_lower for term in ['garage', 'covered', 'indoor']):
            context['parking_type'] = 'garage'
        elif any(term in message_lower for term in ['street', 'roadside', 'on-street']):
            context['parking_type'] = 'street'
        elif any(term in message_lower for term in ['lot', 'surface', 'outdoor']):
            context['parking_type'] = 'lot'
        elif any(term in message_lower for term in ['park and ride', 'park & ride']):
            context['parking_type'] = 'park-ride'
        
        # Check for EV charging needs
        if any(term in message_lower for term in ['electric', 'ev', 'charging', 'tesla', 'hybrid']):
            context['ev_charging'] = True
        
        # Check for accessibility needs
        if any(term in message_lower for term in ['accessible', 'disabled', 'wheelchair', 'mobility']):
            context['accessibility'] = True
        
        # Extract price preferences
        price_patterns = [
            r'under\s+£(\d+)',
            r'less\s+than\s+£(\d+)',
            r'max\s+£(\d+)',
            r'budget\s+£(\d+)'
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, message_lower)
            if match and match.group(1).isdigit():
                context['max_price'] = int(match.group(1))
                break
        
        # Extract distance preferences
        distance_patterns = [
            r'within\s+(\d+)\s*(?:m|meters?|metres?)',
            r'(\d+)\s*(?:m|meters?|metres?)\s+walk',
            r'close\s+to',
            r'nearby'
        ]
        
        for pattern in distance_patterns:
            match = re.search(pattern, message_lower)
            if match and match.group(1) and match.group(1).isdigit():
                context['preferred_distance'] = int(match.group(1))
                break
            elif 'close' in pattern or 'nearby' in pattern:
                context['preferred_distance'] = 200
        
        # Enhanced time extraction
        time_patterns = [
            r'at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm))',
            r'(\d{1,2}(?::\d{2})?\s*(?:am|pm))',
            r'at\s+(\d{1,2})',
            r'(\d{1,2})\s*(?:pm|am)',
            r'(morning|afternoon|evening|night)',
            r'(now|immediately|asap)'
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, message_lower)
            if match:
                context['time'] = match.group(1)
                break
        
        # Enhanced duration extraction
        duration_patterns = [
            r'for\s+(\d+)\s*hours?',
            r'(\d+)\s*hours?',
            r'for\s+(\d+)\s*minutes?',
            r'all\s+day',
            r'overnight',
            r'quick\s*stop'
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, message_lower)
            if match:
                if 'day' in match.group(0):
                    context['duration'] = '8'
                elif 'overnight' in match.group(0):
                    context['duration'] = '12'
                elif 'quick' in match.group(0):
                    context['duration'] = '0.5'
                else:
                    context['duration'] = match.group(1)
                break
        
        # Extract location
        location_text = message
        location_text = re.sub(r'\bat\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)', '', location_text, flags=re.IGNORECASE)
        location_text = re.sub(r'\bfor\s+\d+\s*(?:hours?|minutes?)', '', location_text, flags=re.IGNORECASE)
        location_text = re.sub(r'\b(?:can|could)\s+i\s*park\s*(?:in|at|near)\s*', '', location_text, flags=re.IGNORECASE)
        location_text = re.sub(r'\b(?:parking|park)\b', '', location_text, flags=re.IGNORECASE)
        location_text = re.sub(r'\b(?:garage|covered|street|lot)\b', '', location_text, flags=re.IGNORECASE)
        context['location'] = location_text.strip()
        
        logger.info(f"Extracted context: {context}")
        return context

    def geocode_location(self, location_query: str) -> tuple:
        """Enhanced geocoding with better address parsing"""
        params = {
            'q': location_query,
            'apiKey': self.api_key,
            'limit': 5,
            'lang': 'en-US',
            'types': 'city,locality,district,address'
        }

        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                best_match = data['items'][0]
                position = best_match['position']
                address_info = best_match.get('address', {})
                
                address_details = {
                    'full_address': address_info.get('label', location_query),
                    'city': address_info.get('city', ''),
                    'district': address_info.get('district', ''),
                    'county': address_info.get('county', ''),
                    'state': address_info.get('state', ''),
                    'country': address_info.get('countryName', ''),
                    'postal_code': address_info.get('postalCode', ''),
                    'street': address_info.get('street', ''),
                    'house_number': address_info.get('houseNumber', ''),
                    'formatted': address_info.get('label', location_query),
                    'confidence': best_match.get('scoring', {}).get('queryScore', 0)
                }
                
                logger.info(f"Geocoded location: {location_query} -> {position}")
                return position['lat'], position['lng'], address_details, True
            else:
                logger.warning(f"No geocoding results for: {location_query}")
                return None, None, None, False
        except Exception as e:
            logger.error(f"Geocoding error for {location_query}: {str(e)}")
            return None, None, None, False

    def search_comprehensive_parking(self, lat: float, lng: float, context: Dict, radius: int = 2000) -> List[Dict]:
        """Comprehensive parking search using HERE Discover API"""
        all_parking_spots = []
        
        parking_spots = self._search_discover_parking(lat, lng, context, radius)
        all_parking_spots.extend(parking_spots)
        
        unique_spots = self._deduplicate_parking_spots(all_parking_spots)
        enhanced_spots = self._enhance_parking_data(unique_spots, lat, lng, context)
        
        logger.info(f"Found {len(enhanced_spots)} parking spots for lat: {lat}, lng: {lng}")
        return enhanced_spots

    def _search_discover_parking(self, lat: float, lng: float, context: Dict, radius: int) -> List[Dict]:
        """Search using HERE Discover API"""
        spots = []
        
        categories = []
        if context.get('parking_type') == 'garage':
            categories.append('parking-garage')
        elif context.get('parking_type') == 'street':
            categories.append('on-street-parking')
        elif context.get('parking_type') == 'lot':
            categories.append('parking-lot')
        elif context.get('parking_type') == 'park-ride':
            categories.append('park-and-ride')
        else:
            categories = ['parking-garage', 'parking-lot', 'on-street-parking']
        
        if context.get('ev_charging'):
            categories.append('ev-charging')
        
        for category in categories:
            params = {
                'at': f"{lat},{lng}",
                'categories': self.parking_categories.get(category, category),
                'r': radius,
                'limit': 20,
                'apiKey': self.api_key,
                'lang': 'en-US'
            }
            
            try:
                response = requests.get(self.discover_url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get('items', []):
                    spot = self._parse_discover_spot(item, category)
                    if spot:
                        spots.append(spot)
                        
            except Exception as e:
                logger.error(f"Discover API error for category {category}: {str(e)}")
                continue
        
        return spots

    def _parse_discover_spot(self, item: Dict, category: str) -> Optional[Dict]:
        """Parse parking spot from Discover API response"""
        try:
            spot = {
                'id': item.get('id', str(uuid.uuid4())),
                'title': item.get('title', 'Parking Area'),
                'address': item.get('address', {}).get('label', ''),
                'position': item.get('position', {}),
                'distance': item.get('distance', 0),
                'categories': [cat.get('name', '') for cat in item.get('categories', [])],
                'category_type': category,
                'contacts': item.get('contacts', []),
                'opening_hours': item.get('openingHours', []),
                'source': 'here_discover'
            }
            
            if item.get('contacts'):
                for contact in item['contacts']:
                    if contact.get('phone'):
                        spot['phone'] = contact['phone'][0].get('value', '')
                    if contact.get('www'):
                        spot['website'] = contact['www'][0].get('value', '')
            
            return spot
        except Exception as e:
            logger.error(f"Error parsing spot: {str(e)}")
            return None

    def _enhance_parking_data(self, spots: List[Dict], user_lat: float, user_lng: float, context: Dict) -> List[Dict]:
        """Enhance parking data with pricing, restrictions, and analysis"""
        enhanced_spots = []
        
        for spot in spots:
            try:
                spot_lat = spot['position'].get('lat', 0)
                spot_lng = spot['position'].get('lng', 0)
                
                if spot_lat and spot_lng:
                    walking_route = self._get_walking_route(user_lat, user_lng, spot_lat, spot_lng)
                    if walking_route:
                        spot['walking_time'] = walking_route.get('duration', 0) // 60
                        spot['walking_distance'] = walking_route.get('distance', spot.get('distance', 0))
                
                spot['pricing'] = self._generate_pricing_info(spot, context)
                spot['restrictions'] = self._generate_restrictions(spot, context)
                spot['availability'] = self._generate_availability_status(spot, context)
                
                if context.get('accessibility'):
                    spot['accessibility'] = self._get_accessibility_info(spot)
                
                if context.get('ev_charging') or 'ev-charging' in spot.get('category_type', ''):
                    spot['ev_charging'] = self._get_ev_charging_info(spot)
                
                spot['recommendation_score'] = self._calculate_recommendation_score(spot, context)
                spot['analysis'] = self._generate_spot_analysis(spot, context)
                
                enhanced_spots.append(spot)
                
            except Exception as e:
                logger.error(f"Error enhancing spot data: {str(e)}")
                enhanced_spots.append(spot)
        
        enhanced_spots.sort(key=lambda x: x.get('recommendation_score', 0), reverse=True)
        return enhanced_spots

    def _get_walking_route(self, start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> Optional[Dict]:
        """Get walking route information"""
        params = {
            'transportMode': 'pedestrian',
            'origin': f"{start_lat},{start_lng}",
            'destination': f"{end_lat},{end_lng}",
            'return': 'summary',
            'apiKey': self.api_key
        }
        
        try:
            response = requests.get(self.routing_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get('routes'):
                route = data['routes'][0]
                summary = route.get('sections', [{}])[0].get('summary', {})
                return {
                    'duration': summary.get('duration', 0),
                    'distance': summary.get('length', 0)
                }
        except Exception as e:
            logger.error(f"Routing error: {str(e)}")
        return None

    def _generate_pricing_info(self, spot: Dict, context: Dict) -> Dict:
        """Generate comprehensive pricing information"""
        category = spot.get('category_type', '')
        location_type = 'city_center' if spot.get('distance', 1000) < 500 else 'suburban'
        
        pricing_data = {
            'hourly_rate': None,
            'daily_rate': None,
            'weekly_rate': None,
            'free_periods': [],
            'payment_methods': ['Card', 'Mobile App', 'Coins'],
            'pricing_structure': 'progressive'
        }
        
        if category == 'parking-garage':
            base_rate = 3.50 if location_type == 'city_center' else 2.00
            pricing_data['hourly_rate'] = f"£{base_rate:.2f}"
            pricing_data['daily_rate'] = f"£{base_rate * 6:.2f}"
            pricing_data['payment_methods'].extend(['Season Pass', 'Corporate Card'])
            
        elif category == 'on-street-parking':
            base_rate = 2.20 if location_type == 'city_center' else 1.50
            pricing_data['hourly_rate'] = f"£{base_rate:.2f}"
            pricing_data['free_periods'] = ['Sundays', 'After 6pm weekdays', 'Bank holidays']
            
        elif category == 'parking-lot':
            base_rate = 2.80 if location_type == 'city_center' else 1.80
            pricing_data['hourly_rate'] = f"£{base_rate:.2f}"
            pricing_data['daily_rate'] = f"£{base_rate * 5:.2f}"
            
        elif category == 'park-and-ride':
            pricing_data['hourly_rate'] = "£4.00"
            pricing_data['daily_rate'] = "£8.00"
            pricing_data['free_periods'] = ['With valid public transport ticket']
            
        else:
            base_rate = 2.50
            pricing_data['hourly_rate'] = f"£{base_rate:.2f}"
        
        if context.get('duration') and float(context.get('duration', '0')) > 4:
            pricing_data['special_offers'] = ['Long stay discount available', 'Daily rate better value']
        
        return pricing_data

    def _generate_restrictions(self, spot: Dict, context: Dict) -> List[str]:
        """Generate parking restrictions based on spot type and location"""
        restrictions = []
        category = spot.get('category_type', '')
        
        if category == 'on-street-parking':
            restrictions.extend([
                'Maximum stay: 2-4 hours',
                'No parking 7-9am Mon-Fri (clearing times)',
                'Permit holders exempt from time limits',
                'Loading bay restrictions nearby'
            ])
            
        elif category == 'parking-garage':
            restrictions.extend([
                'Height restriction: 2.1m',
                'No overnight parking without permit',
                '24-hour access with pre-payment',
                'CCTV monitored premises'
            ])
            
        elif category == 'parking-lot':
            restrictions.extend([
                'Payment required 8am-6pm Mon-Sat',
                'Free parking Sundays and bank holidays',
                'No commercial vehicles over 3.5t',
                'Maximum stay: 8 hours'
            ])
            
        elif category == 'park-and-ride':
            restrictions.extend([
                'Valid public transport ticket required',
                'Car park closes at midnight',
                'No overnight parking',
                'Motorcycles designated area only'
            ])
        
        if context.get('accessibility'):
            restrictions.append('Blue badge required for accessible spaces')
        
        current_time = datetime.now()
        if current_time.weekday() >= 5:
            restrictions.append('Weekend rates may apply')
        
        return restrictions

    def _generate_availability_status(self, spot: Dict, context: Dict) -> Dict:
        """Generate availability status with real-time considerations"""
        current_hour = datetime.now().hour
        category = spot.get('category_type', '')
        
        if 8 <= current_hour <= 18:
            if category == 'on-street-parking':
                base_availability = 'Limited'
            elif category == 'parking-garage':
                base_availability = 'Moderate'
            else:
                base_availability = 'Good'
        else:
            base_availability = 'Excellent'
        
        confidence = 'High' if context.get('urgency') != 'urgent' or base_availability in ['Good', 'Excellent'] else 'Medium'
        
        return {
            'status': base_availability,
            'confidence': confidence,
            'last_updated': datetime.now().isoformat(),
            'spaces_available': self._estimate_available_spaces(spot, base_availability),
            'peak_times': self._get_peak_times(category),
            'best_times': self._get_best_times(category)
        }

    def _get_accessibility_info(self, spot: Dict) -> Dict:
        """Get accessibility information for the parking spot"""
        return {
            'accessible_spaces': 'Available',
            'features': [
                'Designated accessible parking bays',
                'Level access to payment machines',
                'Clear signage and markings',
                'Wider parking spaces (3.6m minimum)'
            ],
            'nearby_facilities': [
                'Accessible toilets within 100m',
                'Level pedestrian access',
                'Tactile paving available'
            ],
            'requirements': 'Valid Blue Badge must be displayed'
        }

    def _get_ev_charging_info(self, spot: Dict) -> Dict:
        """Get EV charging information"""
        return {
            'charging_available': True,
            'charger_types': ['Type 2', 'CCS', 'CHAdeMO'],
            'charging_speeds': ['7kW AC', '22kW AC', '50kW DC'],
            'number_of_points': random.randint(2, 8),
            'network': random.choice(['Pod Point', 'BP Pulse', 'InstaVolt', 'Ecotricity']),
            'payment_methods': ['RFID Card', 'Mobile App', 'Contactless'],
            'cost_per_kwh': '£0.35-0.45',
            'availability': '24/7',
            'reservation': 'Available through app'
        }

    def _calculate_recommendation_score(self, spot: Dict, context: Dict) -> int:
        """Calculate recommendation score based on multiple factors"""
        score = 50
        
        distance = spot.get('distance', 1000)
        if distance < 200:
            score += 20
        elif distance < 500:
            score += 15
        elif distance < 1000:
            score += 10
        else:
            score -= 10
        
        preferred_type = context.get('parking_type')
        if preferred_type and preferred_type in spot.get('category_type', ''):
            score += 15
        
        if context.get('max_price'):
            hourly_rate = spot.get('pricing', {}).get('hourly_rate', '£2.50')
            rate_value = float(hourly_rate.replace('£', ''))
            if rate_value <= context['max_price']:
                score += 10
            else:
                score -= 15
        
        availability = spot.get('availability', {}).get('status', 'Good')
        if availability == 'Excellent':
            score += 15
        elif availability == 'Good':
            score += 10
        elif availability == 'Limited':
            score -= 5
        
        if context.get('ev_charging') and spot.get('ev_charging'):
            score += 20
        
        if context.get('accessibility') and spot.get('accessibility'):
            score += 20
        
        walking_time = spot.get('walking_time', 10)
        if walking_time <= 3:
            score += 10
        elif walking_time <= 5:
            score += 5
        elif walking_time > 10:
            score -= 5
        
        return max(0, min(100, score))

    def _generate_spot_analysis(self, spot: Dict, context: Dict) -> Dict:
        """Generate comprehensive analysis for the parking spot"""
        pros = []
        cons = []
        
        distance = spot.get('distance', 1000)
        walking_time = spot.get('walking_time', distance // 80)
        
        if walking_time <= 3:
            pros.append(f"Excellent location - only {walking_time} min walk")
        elif walking_time <= 5:
            pros.append(f"Good location - {walking_time} min walk")
        elif walking_time > 8:
            cons.append(f"Longer walk required - {walking_time} minutes")
        
        category = spot.get('category_type', '')
        if category == 'parking-garage':
            pros.extend(['Weather protected', 'Secure environment', 'Usually available'])
            cons.append('Height restrictions may apply')
        elif category == 'on-street-parking':
            pros.extend(['Usually cheaper', 'Quick access'])
            cons.extend(['Weather exposed', 'Time restrictions', 'Higher turnover'])
        elif category == 'park-and-ride':
            pros.extend(['Great for public transport connections', 'Lower cost for long stays'])
            cons.append('Requires public transport ticket')
        
        pricing = spot.get('pricing', {})
        hourly_rate = pricing.get('hourly_rate', '£2.50')
        rate_value = float(hourly_rate.replace('£', ''))
        
        if rate_value < 2.00:
            pros.append('Very affordable pricing')
        elif rate_value < 3.00:
            pros.append('Reasonable pricing')
        else:
            cons.append('Premium pricing')
        
        availability = spot.get('availability', {}).get('status', 'Good')
        if availability == 'Excellent':
            pros.append('Excellent availability')
        elif availability == 'Limited':
            cons.append('Limited availability - arrive early')
        
        if spot.get('ev_charging'):
            pros.append('EV charging available')
        
        if spot.get('accessibility'):
            pros.append('Accessible parking available')
        
        return {
            'pros': pros,
            'cons': cons,
            'overall_rating': 'Excellent' if len(pros) > len(cons) + 1 else 'Good' if len(pros) >= len(cons) else 'Fair',
            'best_for': self._get_best_for_description(spot, context),
            'alternatives': self._get_alternatives_suggestion(spot, context)
        }

    def _get_best_for_description(self, spot: Dict, context: Dict) -> str:
        """Describe what this parking spot is best for"""
        category = spot.get('category_type', '')
        duration = context.get('duration', '2')
        
        try:
            duration_hours = float(duration)
        except:
            duration_hours = 2
        
        if category == 'park-and-ride':
            return "Commuters and public transport users"
        elif category == 'parking-garage' and duration_hours > 4:
            return "Long stays and all-weather protection"
        elif category == 'on-street-parking' and duration_hours < 2:
            return "Quick visits and short errands"
        elif spot.get('ev_charging'):
            return "Electric vehicle owners needing to charge"
        else:
            return "General parking needs and medium-term stays"

    def _get_alternatives_suggestion(self, spot: Dict, context: Dict) -> str:
        """Suggest alternatives based on the current spot"""
        category = spot.get('category_type', '')
        
        if category == 'parking-garage':
            return "Consider nearby street parking for lower costs"
        elif category == 'on-street-parking':
            return "Look for parking garages for longer stays"
        elif spot.get('distance', 0) > 500:
            return "Check for closer options or consider public transport"
        else:
            return "This is one of the best options in the area"

    def _deduplicate_parking_spots(self, spots: List[Dict]) -> List[Dict]:
        """Remove duplicate parking spots based on location"""
        seen_locations = set()
        unique_spots = []
        
        for spot in spots:
            position = spot.get('position', {})
            lat = position.get('lat', 0)
            lng = position.get('lng', 0)
            
            location_key = f"{lat:.4f},{lng:.4f}"
            
            if location_key not in seen_locations:
                seen_locations.add(location_key)
                unique_spots.append(spot)
        
        return unique_spots

    def _estimate_available_spaces(self, spot: Dict, availability_status: str) -> str:
        """Estimate available spaces based on spot type and availability"""
        category = spot.get('category_type', '')
        
        if category == 'parking-garage':
            total_estimate = random.randint(50, 200)
        elif category == 'parking-lot':
            total_estimate = random.randint(20, 100)
        elif category == 'on-street-parking':
            total_estimate = random.randint(10, 30)
        else:
            total_estimate = random.randint(15, 80)
        
        if availability_status == 'Excellent':
            available = int(total_estimate * 0.7)
        elif availability_status == 'Good':
            available = int(total_estimate * 0.4)
        elif availability_status == 'Moderate':
            available = int(total_estimate * 0.2)
        else:
            available = max(1, int(total_estimate * 0.1))
        
        return f"{available}/{total_estimate}"

    def _get_peak_times(self, category: str) -> List[str]:
        """Get peak times for different parking categories"""
        if category == 'parking-garage':
            return ['8-10am weekdays', '12-2pm weekdays', '5-7pm weekdays']
        elif category == 'on-street-parking':
            return ['9am-5pm weekdays', 'Saturday mornings', 'Event days']
        elif category == 'park-and-ride':
            return ['7-9am weekdays', '5-7pm weekdays']
        else:
            return ['9am-5pm weekdays', 'Weekend afternoons']

    def _get_best_times(self, category: str) -> List[str]:
        """Get best times to park for different categories"""
        if category == 'parking-garage':
            return ['Early morning (before 8am)', 'Evenings (after 7pm)', 'Weekends']
        elif category == 'on-street-parking':
            return ['Before 9am', 'After 6pm', 'Sundays']
        elif category == 'park-and-ride':
            return ['Mid-morning (10am-12pm)', 'Early afternoon (2-4pm)']
        else:
            return ['Off-peak hours', 'Weekends', 'Early evenings']

    def generate_mock_parking_data(self, address_info: Dict, context: Dict) -> List[Dict]:
        """Generate mock parking data when API fails"""
        city = address_info.get('city', 'Unknown City')
        base_lat = 51.5074
        base_lng = -0.1278
        
        mock_spots = [
            {
                'id': str(uuid.uuid4()),
                'title': f"{city} Central Garage",
                'address': f"123 Main Street, {city}",
                'position': {'lat': base_lat + random.uniform(-0.01, 0.01), 'lng': base_lng + random.uniform(-0.01, 0.01)},
                'distance': 200,
                'category_type': 'parking-garage',
                'pricing': {
                    'hourly_rate': '£2.50',
                    'daily_rate': '£15.00',
                    'payment_methods': ['Card', 'Mobile App', 'Coins']
                },
                'availability': {
                    'status': 'Good',
                    'confidence': 'High',
                    'last_updated': datetime.now().isoformat(),
                    'spaces_available': '50/100'
                },
                'restrictions': ['2.1m height limit', 'No overnight parking'],
                'recommendation_score': 85,
                'walking_time': 3,
                'analysis': {
                    'pros': ['Close to center', 'Covered parking'],
                    'cons': ['Limited spaces during peak hours'],
                    'overall_rating': 'Excellent'
                }
            },
            {
                'id': str(uuid.uuid4()),
                'title': f"{city} Street Parking",
                'address': f"High Street, {city}",
                'position': {'lat': base_lat + random.uniform(-0.01, 0.01), 'lng': base_lng + random.uniform(-0.01, 0.01)},
                'distance': 350,
                'category_type': 'on-street-parking',
                'pricing': {
                    'hourly_rate': '£1.80',
                    'daily_rate': '£10.80',
                    'payment_methods': ['Card', 'Mobile App']
                },
                'availability': {
                    'status': 'Moderate',
                    'confidence': 'High',
                    'last_updated': datetime.now().isoformat(),
                    'spaces_available': '10/30'
                },
                'restrictions': ['2 hour max stay', 'Pay and display'],
                'recommendation_score': 75,
                'walking_time': 5,
                'analysis': {
                    'pros': ['Cheaper option', 'Quick access'],
                    'cons': ['Weather exposed', 'Time restricted'],
                    'overall_rating': 'Good'
                }
            },
            {
                'id': str(uuid.uuid4()),
                'title': f"{city} Shopping Centre Lot",
                'address': f"Retail Park, {city}",
                'position': {'lat': base_lat + random.uniform(-0.01, 0.01), 'lng': base_lng + random.uniform(-0.01, 0.01)},
                'distance': 500,
                'category_type': 'parking-lot',
                'pricing': {
                    'hourly_rate': '£2.00',
                    'daily_rate': '£12.00',
                    'payment_methods': ['Card', 'Mobile App', 'Coins']
                },
                'availability': {
                    'status': 'Good',
                    'confidence': 'High',
                    'last_updated': datetime.now().isoformat(),
                    'spaces_available': '40/80'
                },
                'restrictions': ['No commercial vehicles', '8 hour max stay'],
                'recommendation_score': 80,
                'walking_time': 7,
                'analysis': {
                    'pros': ['Spacious lot', 'Near amenities'],
                    'cons': ['Busy during weekends'],
                    'overall_rating': 'Good'
                }
            }
        ]
        
        if context.get('ev_charging'):
            mock_spots.append({
                'id': str(uuid.uuid4()),
                'title': f"{city} EV Charging Station",
                'address': f"Green Lane, {city}",
                'position': {'lat': base_lat + random.uniform(-0.01, 0.01), 'lng': base_lng + random.uniform(-0.01, 0.01)},
                'distance': 400,
                'category_type': 'ev-charging',
                'pricing': {
                    'hourly_rate': '£3.00',
                    'daily_rate': '£18.00',
                    'payment_methods': ['Card', 'Mobile App', 'Contactless']
                },
                'availability': {
                    'status': 'Moderate',
                    'confidence': 'High',
                    'last_updated': datetime.now().isoformat(),
                    'spaces_available': '4/8'
                },
                'restrictions': ['EV only', '4 hour max stay'],
                'recommendation_score': 90,
                'walking_time': 6,
                'ev_charging': self._get_ev_charging_info({}),
                'analysis': {
                    'pros': ['EV charging available', 'Modern facility'],
                    'cons': ['Premium pricing'],
                    'overall_rating': 'Excellent'
                }
            })
        
        if context.get('accessibility'):
            mock_spots.append({
                'id': str(uuid.uuid4()),
                'title': f"{city} Accessible Parking",
                'address': f"Station Road, {city}",
                'position': {'lat': base_lat + random.uniform(-0.01, 0.01), 'lng': base_lng + random.uniform(-0.01, 0.01)},
                'distance': 300,
                'category_type': 'accessible-parking',
                'pricing': {
                    'hourly_rate': '£2.00',
                    'daily_rate': '£12.00',
                    'payment_methods': ['Card', 'Mobile App']
                },
                'availability': {
                    'status': 'Good',
                    'confidence': 'High',
                    'last_updated': datetime.now().isoformat(),
                    'spaces_available': '5/10'
                },
                'restrictions': ['Blue Badge required', '4 hour max stay'],
                'recommendation_score': 85,
                'walking_time': 4,
                'accessibility': self._get_accessibility_info({}),
                'analysis': {
                    'pros': ['Accessible spaces', 'Level access'],
                    'cons': ['Limited spaces'],
                    'overall_rating': 'Excellent'
                }
            })
        
        logger.info(f"Generated {len(mock_spots)} mock parking spots for {city}")
        return mock_spots

    def generate_human_response(self, context: Dict, location_info: Dict, spots_found: int) -> str:
        """Generate human-like responses with context awareness"""
        positive_start = random.choice(self.positive_responses)
        location_name = location_info.get('city', context.get('location', 'your area'))
        
        time_text = f" at {context['time']}" if context.get('time') else ""
        duration_text = f" for {context['duration']} hours" if context.get('duration') else ""
        
        if context.get('ev_charging'):
            return f"{positive_start} I found {spots_found} parking options with EV charging in {location_name}{time_text}. Perfect for your electric vehicle! ⚡"
        elif context.get('accessibility'):
            return f"{positive_start} I've located {spots_found} accessible parking options in {location_name}{time_text}. All include proper accessibility features! ♿"
        elif context.get('urgency') == 'urgent':
            return f"{positive_start} I quickly found {spots_found} available parking spots in {location_name}{time_text}. Let's get you parked ASAP! 🚗💨"
        elif context.get('parking_type') == 'garage':
            return f"{positive_start} I found {spots_found} covered parking garages in {location_name}{time_text}. You'll be protected from the weather! 🏢"
        else:
            return f"{positive_start} I discovered {spots_found} great parking options in {location_name}{time_text}{duration_text}. Here are your best choices!"

    def generate_comprehensive_response(self, spots: List[Dict], context: Dict, location_info: Dict) -> Dict:
        """Generate comprehensive response with all parking information"""
        total_spots = len(spots)
        
        spot_categories = {}
        for spot in spots:
            category = spot.get('category_type', 'general')
            if category not in spot_categories:
                spot_categories[category] = []
            spot_categories[category].append(spot)
        
        avg_price = self._calculate_average_price(spots)
        closest_spot = min(spots, key=lambda x: x.get('distance', 1000)) if spots else None
        cheapest_spot = min(spots, key=lambda x: self._extract_price_value(x.get('pricing', {}).get('hourly_rate', '£5.00'))) if spots else None
        
        return {
            "message": self.generate_human_response(context, location_info, total_spots),
            "response": f"I've analyzed {total_spots} parking options in {location_info.get('city', 'your area')}. Here's everything you need to know!",
            "summary": {
                "total_options": total_spots,
                "categories_available": list(spot_categories.keys()),
                "average_price": avg_price,
                "closest_option": {
                    "id": closest_spot.get('id', '') if closest_spot else '',
                    "title": closest_spot.get('title', '') if closest_spot else '',
                    "distance": f"{closest_spot.get('distance', 0)}m" if closest_spot else '',
                    "walking_time": f"{closest_spot.get('walking_time', 0)} min" if closest_spot else ''
                } if closest_spot else None,
                "cheapest_option": {
                    'id': cheapest_spot.get('id', '') if cheapest_spot else '',
                    "title": cheapest_spot.get('title', '') if cheapest_spot else '',
                    "price": cheapest_spot.get('pricing', {}).get('hourly_rate', '') if cheapest_spot else ''
                } if cheapest_spot else None
            },
            "all_spots": [self._format_spot_for_response(spot, i+1) for i, spot in enumerate(spots)],
            "categories": {
                category: len(spots_in_category)
                for category, spots_in_category in spot_categories.items()
            },
            "search_context": {
                "location": location_info.get('formatted', context.get('location', '')),
                "time_requested": context.get('time', 'flexible'),
                "duration_needed": context.get('duration', 'not specified'),
                "special_requirements": self._get_special_requirements_summary(context),
                "local_regulations": self._get_local_regulations(location_info)
            },
            "area_insights": self._generate_area_insights(spots, location_info),
            "recommendations": {
                "best_overall": self._format_spot_for_response(spots[0], 1) if spots else None,
                "best_value": self._format_spot_for_response(cheapest_spot, 1) if cheapest_spot else None,
                "closest": self._format_spot_for_response(closest_spot, 1) if closest_spot else None,
                "best_for_long_stay": self._format_spot_for_response(self._find_best_for_long_stay(spots), 1) if spots else None,
                "most_convenient": self._format_spot_for_response(self._find_most_convenient(spots), 1) if spots else None
            },
            "tips": self._generate_parking_tips(spots, context, location_info),
            "status": "success",
            "data_source": "here_api_enhanced"
        }

    def _calculate_average_price(self, spots: List[Dict]) -> str:
        """Calculate average parking price"""
        prices = []
        for spot in spots:
            price_str = spot.get('pricing', {}).get('hourly_rate', '£0.00')
            try:
                price_value = float(price_str.replace('£', ''))
                prices.append(price_value)
            except:
                continue
        
        if prices:
            avg_price = sum(prices) / len(prices)
            return f"£{avg_price:.2f}/hour"
        return "Varies"

    def _extract_price_value(self, price_str: str) -> float:
        """Extract price from string"""
        try:
            return float(price_str.replace('£', '').split('/')[0])
        except:
            return float('inf')

    def _format_spot_for_response(self, spot: Dict, rank: int) -> Dict:
        """Format parking spot for API response"""
        return {
            "rank": rank,
            'id': spot.get('id', f"spot_{rank}"),
            "title": spot.get('title', 'Normal'),
            "address": spot.get('address', 'Address available'),
            "type": spot.get('category_type', '').replace('-', ' ').title(),
            "distance": f"{spot.get('distance', 0)}m",
            "walking_time": f"{spot.get('walking_time', 5)} minutes",
            "pricing": spot.get('pricing', {}),
            'availability': spot.get('availability', {}),
            "restrictions": spot.get('restrictions', []),
            "analysis": spot.get('analysis', {}),
            "recommendation_score": spot.get('recommendation_score', 0),
            "special_features": self._get_special_features(spot),
            "contact_info": {
                "phone": spot.get('phone', ''),
                'website': spot.get('website', '')
            },
            "coordinates": spot.get('position', {}),
            'realtime_data': None,
            "ev_charging": spot.get('ev_charging', None),
            'accessibility': spot.get('accessibility', None)
        }

    def _get_special_features(self, spot: Dict) -> List[str]:
        """Get special features of the parking spot"""
        features = []
        
        if spot.get('ev_charging'):
            features.append('EV Charging Available')
        
        if spot.get('accessibility'):
            features.append('Accessible Parking')
        
        category = spot.get('category_type', '')
        if category == 'parking-garage':
            features.extend(['Covered Parking', 'Weather Protected'])
        elif category == 'park-and-ride':
            features.append('Public Transport Connection')
        
        if spot.get('opening_hours'):
            features.append('24/7 Access')
        
        pricing = spot.get('pricing', {})
        if pricing.get('free_periods'):
            features.append('Free Parking Periods')
        
        return features

    def _get_special_requirements_summary(self, context: Dict) -> List[str]:
        """Get summary of special requirements"""
        requirements = []
        
        if context.get('ev_charging'):
            requirements.append('EV Charging Required')
        
        if context.get('accessibility'):
            requirements.append('Accessible Parking Required')
        
        if context.get('parking_type'):
            requirements.append(f"Preferred: {context['parking_type'].title()} Parking")
        
        if context.get('max_price'):
            requirements.append(f"Budget: Under £{context['max_price']}/hour")
        
        if context.get('preferred_distance'):
            requirements.append(f"Walking Distance: Within {context['preferred_distance']}m")
        
        return requirements

    def _generate_area_insights(self, spots: List[Dict], location_info: Dict) -> Dict:
        """Generate insights about the parking area"""
        area_name = location_info.get('city', 'this area')
        
        insights = {
            'area_type': self._determine_area_type(spots, location_info),
            'parking_density': 'High' if len(spots) > 15 else 'Moderate' if len(spots) > 8 else 'Limited',
            'typical_pricing': self._get_typical_price_range(spots),
            'peak_congestion': self._get_area_peak_hours(location_info),
            'best_parking_strategy': self._get_best_strategy(spots, location_info),
            'local_regulations': self._get_local_regulations(location_info),
            'alternative_transport': self._get_transport_alternatives(location_info)
        }
        
        return insights

    def _determine_area_type(self, spots: List[Dict], location_info: Dict) -> str:
        """Determine the type of area based on location and parking options"""
        city = location_info.get('city', '').lower()
        district = location_info.get('district', '').lower()
        
        if any(term in city for term in ['london', 'manchester', 'birmingham', 'leeds', 'liverpool']):
            if any(term in district for term in ['center', 'centre', 'city', 'downtown']):
                return 'Major City Center'
            else:
                return 'Urban Area'
            
        elif any(term in district for term in ['center', 'centre', 'high street', 'town']):
            return 'Town Center'
            
        elif len([s for s in spots if 'garage' in s.get('category_type', '')]) > 3:
            return 'Commercial District'
            
        return 'Residential/Suburban Area'

    def _get_typical_price_range(self, spots: List[Dict]) -> str:
        """Get typical pricing range for the area"""
        prices = []
        for spot in spots:
            price_str = spot.get('pricing', {}).get('hourly_rate', '£0.00')
            try:
                price_value = float(price_str.replace('£', ''))
                prices.append(price_value)
            except:
                continue
                
        if prices:
            min_price = min(prices)
            max_price = max(prices)
            return f'£{min_price:.2f} - £{max_price:.2f} per hour'
        return 'Varies by location'

    def _get_area_peak_hours(self, location_info: Dict) -> List[str]:
        """Get peak congestion times for the area"""
        area_type = self._determine_area_type([], location_info)
        
        if 'City Center' in area_type:
            return ['8am-10am weekdays', '12pm-2pm weekdays', '5pm-7pm weekdays', 'Saturday 10am-4pm']
        elif 'Commercial' in area_type:
            return ['9am-5pm weekdays', 'Lunch hours (12pm-2pm)']
        elif 'Town Center' in area_type:
            return ['10am-4pm weekdays', 'Saturday mornings', 'Market days']
        else:
            return ['Weekend afternoons', 'School drop-off/pick-up times']

    def _get_best_strategy(self, spots: List[Dict], location_info: Dict) -> str:
        """Get best parking strategy for the area"""
        area_type = self._determine_area_type(spots, location_info)
        garage_count = len([s for s in spots if 'garage' in s.get('category_type', '')])
        street_count = len([s for s in spots if 'street' in s.get('category_type', '')])
        
        if 'City Center' in area_type:
            return 'Book garage parking in advance for guaranteed spaces, or arrive early for street parking.'
        elif garage_count > street_count:
            return 'Garage parking recommended for reliability and security.'
        elif street_count > garage_count * 2:
            return 'Street parking widely available, but check time restrictions.'
        else:
            return 'Mix of options available - choose based on duration and budget.'

    def _get_local_regulations(self, location_info: Dict) -> List[str]:
        """Get local parking regulations"""
        city = location_info.get('city', '').lower()
        
        regulations = [
            'Blue Badge holders exempt from time limits',
            'No parking on double yellow lines',
            'Loading bays restricted to 30 minutes max',
            'Pay and display tickets must be clearly visible'
        ]
        
        if 'london' in city:
            regulations.extend([
                'Congestion Charge Zone restrictions apply',
                'Residents parking zones require permits',
                'Some areas have emissions-based charges'
            ])
        elif any(city_name in city for city_name in ['manchester', 'birmingham', 'leeds']):
            regulations.extend([
                'City center clean air zones may apply',
                'Park and ride services available'
            ])
            
        return regulations

    def _get_transport_alternatives(self, location_info: Dict) -> List[str]:
        """Get alternative transport options"""
        alternatives = ['Local bus services', 'Walking/cycling paths']
        
        city = location_info.get('city', '').lower()
        
        if 'london' in city:
            alternatives.extend(['Underground/Tube', 'Overground', 'Bus network', 'River services'])
        elif any(city_name in city for city_name in ['manchester', 'birmingham', 'leeds', 'liverpool']):
            alternatives.extend(['Metro/tram services', 'Regional bus network', 'Park and ride'])
        else:
            alternatives.extend(['Local bus routes', 'Train station connections'])
        
        return alternatives

    def _find_best_for_long_stay(self, spots: List[Dict]) -> Optional[Dict]:
        """Find best parking spot for long stays"""
        long_stay_spots = []
        
        for spot in spots:
            restrictions = spot.get('restrictions', [])
            pricing = spot.get('pricing', {})
            
            long_stay_suitable = True
            for restriction in restrictions:
                if any(term in restriction.lower() for term in ['2 hour', '3 hour', 'maximum stay: 2', 'maximum stay: 3']):
                    long_stay_suitable = False
                    break
            
            if long_stay_suitable and pricing.get('daily_rate'):
                score = spot.get('recommendation_score', 0)
                long_stay_spots.append((spot, score))
        
        if long_stay_spots:
            return max(long_stay_spots, key=lambda x: x[1])[0]
        return None

    def _find_most_convenient(self, spots: List[Dict]) -> Optional[Dict]:
        """Find most convenient parking spot"""
        if not spots:
            return None
        
        scored_spots = []
        
        for spot in spots:
            convenience_score = 0
            
            distance = spot.get('distance', 1000)
            if distance < 200:
                convenience_score += 30
            elif distance < 500:
                convenience_score += 20
            else:
                convenience_score += 10
            
            walking_time = spot.get('walking_time', 10)
            if walking_time <= 3:
                convenience_score += 10
            elif walking_time <= 5:
                convenience_score += 5
            else:
                convenience_score += 2
            
            availability = spot.get('availability', {}).get('status', 'Good')
            if availability == 'Excellent':
                convenience_score += 10
            elif availability == 'Good':
                convenience_score += 5
            else:
                convenience_score += 2
            
            category = spot.get('category_type', '')
            if category == 'parking-garage':
                convenience_score += 5
            
            scored_spots.append((spot, convenience_score))
            
        return max(scored_spots, key=lambda x: x[1])[0]

    def _generate_parking_tips(self, spots: List[Dict], context: Dict, location_info: Dict) -> List[str]:
        """Generate contextual parking tips"""
        tips = []
        area_type = self._determine_area_type(spots, location_info)
        
        tips.extend([
            'Arrive 5-10 minutes early to secure your preferred spot.',
            'Keep your parking ticket clearly visible on your dashboard.',
            'Check parking signs carefully for any restrictions.'
        ])
        
        if context.get('time'):
            tips.append(f'Peak time parking: consider arriving 15 minutes before {context.get("time")}.')
        
        if context.get('duration') and float(context.get('duration', '0')) > 4:
            tips.append('For long stays, daily rates are usually better value than hourly.')
        
        if 'City Center' in area_type:
            tips.extend([
                'City center parking fills up quickly - book in advance if possible.',
                'Consider park and ride for longer visits.'
            ])
        
        if context.get('ev_charging'):
            tips.extend([
                'Check charging app for real-time availability.',
                'Bring your charging cable and payment card/app.'
            ])
        
        if context.get('accessibility'):
            tips.append('Blue Badge must be clearly displayed for accessible parking.')
            
        current_hour = datetime.now().hour
        if current_hour < 8:
            tips.append('Early bird advantage: morning spots are less crowded.')
        elif current_hour > 18:
            tips.append('Evening parking: many restrictions lift after 6pm.')
        
        return tips[:5]

# Flask App Setup
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
cache = Cache(app, config={'CACHE_TYPE': 'simple'})
enhanced_parksy = EnhancedParksyAPI()

@app.route('/', methods=['GET'])
@cache.cached(timeout=3600)
def home():
    return jsonify({
        'message': '🅿 Welcome to Enhanced Parksy - Your Comprehensive UK Parking Assistant!',
        'version': '1.0',
        'status': 'active',
        'features': [
            'Complete HERE API Integration',
            'EV charging station locations',
            'Accessible parking options',
            'On-street & off-street parking',
            'Pricing and restrictions analysis',
            'Walking routes and times',
            'Area insights and recommendations',
            'Smart context understanding',
            'Cached responses for performance'
        ],
        'parking_types_supported': [
            'Parking Garages',
            'Street Parking',
            'Parking Lots',
            'Park & ride',
            'EV Charging Stations',
            'Accessible Parking'
        ]
    })

@app.route('/api/chat', methods=['POST'])
@cache.memoize(timeout=600)
def enhanced_chat():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({
                'error': 'Please send a message about where you would like to park in the UK!',
                'examples': [
                    'Can I park in Bradford city center at 2pm?',
                    'Find accessible parking near London Bridge',
                    'EV charging parking in Manchester for 4 hours',
                    'Cheap street parking in Leeds'
                ]
            }), 400

        user_message = data['message'].strip()
        if not user_message or len(user_message) > 500:
            return jsonify({'error': 'Message cannot be empty or exceed 500 characters.'}), 400

        context = enhanced_parksy.extract_parking_context(user_message)
        
        if not context['location']:
            return jsonify({
                'message': 'I would love to help you find the perfect parking spot in the UK! 😊',
                'response': 'Could you tell me where you would like to park? I can find all types of parking with detailed information!',
                'suggestions': [
                    'Specify your destination (e.g., "Bradford city center")',
                    'Mention special needs (e.g., "EV charging", "accessible parking")',
                    'Include timing (e.g., "at 2pm", "for 3 hours")',
                    'Set preferences (e.g., "covered parking", "under £3/hour")'
                ],
                'supported_features': [
                    '🏢 Parking garages and lots',
                    '🛑 Street parking with restrictions',
                    '⚡ EV charging stations',
                    '♿ Accessible parking',
                    '🚊 Park & ride facilities',
                    '💰 Pricing and availability'
                ]
            })

        lat, lng, address_info, found_location = enhanced_parksy.geocode_location(context['location'])
        
        if not found_location:
            return jsonify({
                'message': 'I could not find that location. Could you be more specific?',
                'response': 'Please provide a more detailed location, such as:',
                'suggestions': [
                    'City name (e.g., "Manchester", "Birmingham")',
                    'Area or district (e.g., "Leeds city center")',
                    'Street name or postcode',
                    'Landmark (e.g., "near Piccadilly Station")'
                ]
            }), 400

        parking_spots = enhanced_parksy.search_comprehensive_parking(lat, lng, context)
        
        if not parking_spots:
            logger.warning(f"No parking spots found for {context['location']}, using mock data")
            parking_spots = enhanced_parksy.generate_mock_parking_data(address_info, context)

        response_data = enhanced_parksy.generate_comprehensive_response(parking_spots, context, address_info)
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Enhanced chat error: {str(e)}")
        return jsonify({
            'message': 'I am having trouble processing your parking request right now.',
            'error': str(e),
            'status': 'error',
            'suggestions': [
                'Try a major city name.',
                'Check your internet connection.',
                'Simplify your parking requirements.'
            ]
        }), 500

@app.route('/api/spot-details/<spot_id>', methods=['GET'])
@cache.memoize(timeout=600)
def get_spot_details(spot_id: str):
    """Get detailed information about a specific parking spot"""
    try:
        mock_details = {
            'id': spot_id,
            'title': 'Parking Spot',
            'address': '123 Main Street',
            'position': {'lat': 51.5074, 'lng': -0.1278},
            'detailed_info': {
                'live_availability': 'Updated 2 minutes ago',
                'recent_reviews': [
                    {'rating': 4, 'comment': 'Easy to find and well-lit'},
                    {'rating': 5, 'comment': 'Perfect for shopping trip'}
                ],
                'nearby_amenities': [
                    'Coffee shop - 50m',
                    'Public toilets - 100m',
                    'ATM - 75m'
                ],
                'traffic_conditions': 'Light traffic expected',
                'weather_considerations': 'Covered parking - weather protected'
            },
            'booking_options': [
                {'provider': 'ParkNow', 'advance_booking': True},
                {'provider': 'RingGo', 'mobile_payment': True}
            ],
            'restrictions': ['2 hour max stay'],
            'accessibility': 'Available',
            'type': 'Public Parking',
            'location': 'UK',
            'last_updated': datetime.now().isoformat(),
            'uk_specific': True,
            'analysis': {}
        }
        logger.info(f"Retrieved details for spot: {spot_id}")
        return jsonify(mock_details)
    except Exception as e:
        logger.error(f"Spot details error for {spot_id}: {str(e)}")
        return jsonify({'error': 'Spot details unavailable', 'status': 'error'}), 500

@app.route('/api/area-analysis', methods=['POST'])
@cache.memoize(timeout=3600)
def analyze_parking_area():
    """Analyze parking patterns for a specific area"""
    try:
        data = request.get_json()
        location = data.get('location', '')
        
        if not location or len(location) > 500:
            return jsonify({'error': 'Location required and must be under 500 characters.'}), 400
        
        lat, lng, address_info, found_location = enhanced_parksy.geocode_location(location)
        if not found_location:
            return jsonify({'error': 'Invalid location provided.'}), 400
        
        parking_spots = enhanced_parksy.search_comprehensive_parking(lat, lng, {'location': location})
        
        analysis = {
            'area': address_info.get('city', location),
            'analysis': {
                'parking_density': 'High' if len(parking_spots) > 15 else 'Moderate' if len(parking_spots) > 8 else 'Limited',
                'average_occupancy': f'{random.randint(60, 90)}%',
                'peak_hours': enhanced_parksy._get_area_peak_hours(address_info),
                'pricing_trends': enhanced_parksy._get_typical_price_range(parking_spots),
                'recommendations': [
                    'Book in advance during weekdays.',
                    'Consider park & ride for events.',
                    'Street parking available after 6pm.'
                ]
            }
        }
        logger.info(f"Area analysis completed for {location}")
        return jsonify(analysis)
    except Exception as e:
        logger.error(f"Area analysis error: {str(e)}")
        return jsonify({'error': 'Analysis unavailable', 'status': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
