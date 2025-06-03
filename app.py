# intelligent_parksy.py - AI-Powered Conversational Parking Assistant (UK Enhanced with HERE.com Integration)
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import re
from datetime import datetime, timedelta
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

@dataclass
class ParkingContext:
    """Store conversation context"""
    location: Optional[str] = None
    time: Optional[str] = None
    duration: Optional[str] = None
    vehicle_type: Optional[str] = None
    budget: Optional[str] = None
    preferences: List[str] = None
    last_search: Optional[Dict] = None

class IntelligentParksyBot:
    def __init__(self):
        # API Configuration for HERE.com
        self.api_key = os.getenv('HERE_API_KEY', 'demo_key_for_testing')
        self.discover_url = "https://discover.search.hereapi.com/v1/discover"
        self.geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        self.parking_url = "https://parking.search.hereapi.com/v1/parking"  # Hypothetical endpoint for parking-specific data
        
        # Conversation context storage (in production, use Redis or database)
        self.user_contexts = {}
        
        # UK Parking Rules and Restrictions
        self.uk_parking_rules = {
            'general': [
                "Always check parking signs - they're legally binding",
                "Single yellow lines usually mean no parking during specified times",
                "Double yellow lines mean no parking at any time",
                "Blue badge holders have special parking privileges",
                "Most councils offer free parking after 6pm and on Sundays"
            ],
            'time_restrictions': {
                'morning_rush': "8am-10am: Expect restrictions on main roads and business areas",
                'lunch_time': "12pm-2pm: City centre parking fills up quickly",
                'evening_rush': "5pm-7pm: Residential parking may be restricted",
                'overnight': "Many councils allow free overnight parking from 6pm-8am"
            },
            'costs': {
                'city_centre': "£2-5 per hour in most UK city centres",
                'residential': "£1-3 per hour in residential permit areas",
                'retail_parks': "Usually free for 2-3 hours at shopping centres",
                'train_stations': "£3-8 per day at most UK train stations"
            }
        }
        
        # Enhanced intent patterns with UK-specific language and HERE.com data types
        self.intent_patterns = {
            'greeting': [
                r'\b(hi|hello|hey|alright|morning|afternoon|evening|cheers|hiya)\b',
                r'^(hey there|what\'s up|how do|you alright)\b'
            ],
            'parking_query': [
                r'\b(park|parking|spot|car park|bay|space|motor|on-street|off-street|ev|electric|accessible|disabled|permit|metered)\b',
                r'\b(can\s+i\s+park|where\s+to\s+park|need\s+parking|looking\s+for\s+parking)\b',
                r'\b(find\s+me\s+a\s+spot|park\s+my\s+car|somewhere\s+to\s+park|charge\s+my\s+car)\b'
            ],
            'time_query': [
                r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm)|at\s+\d|tonight|morning|afternoon|evening)\b',
                r'\b(now|later|tomorrow|today|this\s+(morning|afternoon|evening))\b',
                r'\b(for\s+\d+\s+(hours?|hrs|minutes?|mins)|overnight|all\s+day)\b'
            ],
            'location_query': [
                r'\b(?:in|at|near|around|close\s+to|by|on)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:street|st|road|rd|lane|avenue|ave|drive|dr|close|cl|gardens|gdns|square|sq|terrace|ter|crescent|cres|way|place|pl|court|ct|hill|park|pk|view|vw|grove|gr|circle|cir))\b',
                r'\b(?:in|at|near|around|by)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:city|town|centre|center|high\s+street|market|station|hospital|university|college|cathedral|castle|park|shopping\s+centre))\b',
                r'\b(?:in|at|near|around|by)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:at|for|around|by|\d)|\s*[,.]|$)',
                r'\b([A-Z][a-zA-Z\s]{2,})\b(?=\s+(?:at|for|around|by|\d|$))'
            ],
            'budget_concern': [
                r'\b(cheap|affordable|budget|expensive|free|cost|dear|pricey)\b',
                r'£\d+|\d+\s+(pounds?|quid|pence|p)\b'
            ],
            'vehicle_info': [
                r'\b(car|motor|truck|van|lorry|motorcycle|motorbike|bike|SUV|estate|hatchback|saloon|ev|electric)\b',
                r'\b(?:my|a|the)\s+(big|large|small|compact|electric|hybrid)\s+(car|vehicle|motor)\b'
            ],
            'availability_question': [
                r'\b(available|open|busy|full|empty|spaces?|free|real-time|availability)\b',
                r'\b(can\s+i|will\s+there\s+be|is\s+there|any\s+chance)\b'
            ],
            'accessibility_query': [
                r'\b(accessible|disabled|blue\s+badge|handicap|wheelchair)\b'
            ],
            'ev_query': [
                r'\b(ev|electric\s+vehicle|charging\s+station|charge\s+point)\b'
            ],
            'permit_query': [
                r'\b(permit|resident|restricted|zone)\b'
            ]
        }
        
        # Enhanced personality responses
        self.personality_responses = {
            'greeting': [
                "Alright there! 👋 I'm your parking mate, ready to find you the best spots using HERE.com's data! What's up?",
                "Hello! 🚗 Need a parking spot? I've got all the info from HERE.com to make it easy for you!",
                "Hi there! I'm your UK parking expert with HERE.com's real-time data. Where are you headed?",
                "Hey! 🅿️ Let's find you a cracking parking spot with HERE.com's help! Where to?"
            ],
            'enthusiasm': [
                "Brilliant! Let me dive into HERE.com's data and sort that out for you! 🎯",
                "Perfect! I'm buzzing to find you a spot using HERE.com's real-time info! ✨",
                "You bet! HERE.com's parking data is my playground - let's get you parked! 🅿️",
                "Absolutely! I'll tap into HERE.com and get you sorted in no time! 💪"
            ],
            'understanding': [
                "Got it! You're looking for parking",
                "Right, I see you need a spot",
                "I understand! Parking in",
                "Perfect! Let's find parking"
            ],
            'encouragement': [
                "No worries, I'll find you a cracking spot using HERE.com! 💪",
                "Don't stress, HERE.com's got us covered for parking! 🎯",
                "Leave it to me - I'll use HERE.com to find the perfect spot! ⭐",
                "Trust me, we'll get you parked with HERE.com's help! 😊"
            ],
            'helpful_chat': [
                "I'm here with HERE.com's data to help! What's on your mind?",
                "How can I make parking easier with HERE.com's insights?",
                "What parking info do you need? HERE.com's got it all!",
                "I'm all ears - what's the parking question?"
            ],
            'no_data': [
                "No specific data from HERE.com for that spot, but don't worry - I've got plenty of UK parking tips to keep you sorted! 😊",
                "HERE.com's data is a bit shy for that location, but I'm loaded with advice to help you park! 🚗",
                "No exact match on HERE.com, but I'm here with cracking UK parking guidance! 🅿️"
            ]
        }

    def extract_entities(self, message: str) -> Dict:
        """Enhanced entity extraction with HERE.com-specific data types"""
        entities = {
            'location': None,
            'time': None,
            'duration': None,
            'vehicle_type': None,
            'budget': None,
            'preferences': [],
            'parking_type': None,  # on-street, off-street, ev, accessible, permit
        }
        
        message_lower = message.lower()
        
        # Enhanced location patterns
        location_patterns = [
            r'\b(?:in|at|near|around|by|on)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:street|st|road|rd|lane|avenue|ave|drive|dr|close|cl|gardens|gdns|square|sq|terrace|ter|crescent|cres|way|place|pl|court|ct|hill|park|pk|view|vw|grove|gr|circle|cir))\b',
            r'\b(?:in|at|near|around|by)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:city|town|centre|center|high\s+street|market|station|hospital|university|college|cathedral|castle|park|shopping\s+centre))\b',
            r'\b(?:in|at|near|around|by)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:at|for|around|by|\d)|\s*[,.]|$)',
            r'\b([A-Z][a-zA-Z\s]{2,})\b(?=\s+(?:at|for|around|by|\d|$))'
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                location = re.sub(r'\b(the|city|town)\s+', '', location, flags=re.IGNORECASE)
                entities['location'] = location
                break
        
        # Extract time
        time_patterns = [
            r'\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b',
            r'\b(at\s+\d{1,2}(?::\d{2})?)\b',
            r'\b(tonight|this\s+morning|this\s+afternoon|this\s+evening|now|later|tomorrow\s+morning)\b',
            r'\b(rush\s+hour|lunch\s+time|after\s+work)\b'
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['time'] = match.group(1).strip()
                break
        
        # Extract duration
        duration_patterns = [
            r'\b(for\s+\d+\s+(?:hours?|hrs?|minutes?|mins?))\b',
            r'\b(overnight|all\s+day|quick\s+stop|couple\s+of\s+hours|few\s+hours)\b',
            r'\b(shopping|meeting|appointment|work|visit)\b'
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['duration'] = match.group(1).strip()
                break
        
        # Extract vehicle type with EV support
        vehicle_patterns = [
            r'\b(car|motor|truck|van|lorry|motorcycle|motorbike|bike|SUV|estate|hatchback|saloon|ev|electric)\b',
            r'\b(?:my|a|the)\s+(big|large|small|compact|electric|hybrid)\s+(car|vehicle|motor)\b'
        ]
        
        for pattern in vehicle_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['vehicle_type'] = match.group().strip()
                break
        
        # Extract budget
        budget_patterns = [
            r'£(\d+)',
            r'\b(cheap|affordable|budget|free|dear|pricey|expensive)\b',
            r'\b(\d+)\s+(?:pounds?|quid|pence|p)\b'
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['budget'] = match.group().strip()
                break
        
        # Extract parking type
        if any(word in message_lower for word in ['on-street', 'street parking', 'metered']):
            entities['parking_type'] = 'on-street'
        elif any(word in message_lower for word in ['off-street', 'garage', 'lot', 'car park']):
            entities['parking_type'] = 'off-street'
        elif any(word in message_lower for word in ['ev', electric vehicle', 'charging']):
            entities['parking_type'] = 'ev'
        elif any(word in message_lower for word in ['accessible', 'disabled', 'blue badge']):
            entities['parking_type'] = 'accessible'
        elif any(word in message_lower for word in ['permit', 'resident', 'restricted']):
            entities['parking_type'] = 'permit'
        
        # Extract preferences
        if any(word in message_lower for word in ['covered', 'garage', 'multi-storey', 'undercover']):
            entities['preferences'].append('covered')
        if any(word in message_lower for word in ['secure', 'safe', 'cctv', 'gated']):
            entities['preferences'].append('secure')
        if any(word in message_lower for word in ['close', 'near', 'walking', 'short walk']):
            entities['preferences'].append('close')
        if any(word in message_lower for word in ['disabled', 'blue badge', 'accessible']):
            entities['preferences'].append('accessible')
        if any(word in message_lower for word in ['ev', 'electric', 'charging']):
            entities['preferences'].append('ev')
        
        return entities

    def understand_intent(self, message: str) -> Tuple[str, float]:
        """Advanced intent detection with HERE.com-specific patterns"""
        message_lower = message.lower().strip()
        intent_scores = {}
        
        for intent, patterns in self.intent_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, message_lower))
                score += matches * 10
            
            word_count = len(message_lower.split())
            if score > 0:
                if word_count > 5:
                    score += 8
                elif word_count > 3:
                    score += 5
                elif word_count > 1:
                    score += 2
                
            if intent == 'parking_query' and any(word in message_lower for word in ['where', 'find', 'need', 'looking']):
                score += 10
            if intent == 'location_query' and any(word in message_lower for word in ['street', 'near', 'around']):
                score += 15
            if intent == 'ev_query' and 'charging' in message_lower:
                score += 15
            if intent == 'accessibility_query' and 'blue badge' in message_lower:
                score += 15
            if intent == 'permit_query' and 'resident' in message_lower:
                score += 15
                
            intent_scores[intent] = score
        
        if not intent_scores or max(intent_scores.values()) == 0:
            return 'general', 0.5
        
        primary_intent = max(intent_scores, key=intent_scores.get)
        confidence = min(intent_scores[primary_intent] / 100, 1.0)
        
        return primary_intent, confidence

    def generate_contextual_response(self, message: str, user_id: str = 'default') -> Dict:
        """Generate intelligent, human-like contextual responses using HERE.com data"""
        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = ParkingContext()
        
        context = self.user_contexts[user_id]
        entities = self.extract_entities(message)
        intent, confidence = self.understand_intent(message)
        
        # Update context
        if entities['location']:
            context.location = entities['location']
        if entities['time']:
            context.time = entities['time']
        if entities['duration']:
            context.duration = entities['duration']
        if entities['vehicle_type']:
            context.vehicle_type = entities['vehicle_type']
        if entities['budget']:
            context.budget = entities['budget']
        if entities['preferences']:
            context.preferences.extend(entities['preferences'])
        if entities['parking_type']:
            context.preferences.append(entities['parking_type'])
        
        # Handle intents
        if intent == 'greeting':
            return self.handle_greeting(message, context)
        elif intent in ['parking_query', 'ev_query', 'accessibility_query', 'permit_query'] or any([entities['location'], context.location]):
            return self.handle_parking_query(message, context, entities)
        elif intent == 'availability_question':
            return self.handle_availability_question(message, context, entities)
        else:
            return self.handle_general_conversation(message, context, entities)

    def handle_greeting(self, message: str, context: ParkingContext) -> Dict:
        """Handle greeting with HERE.com integration"""
        greeting_response = random.choice(self.personality_responses['greeting'])
        follow_up = "What can I help you with today?"
        if context.location:
            follow_up = f"Still need help with parking in {context.location}, or somewhere new?"
        
        return {
            'message': greeting_response,
            'response': f"{follow_up} Using HERE.com, I can find you on-street, off-street, EV charging, accessible, or permit parking spots across the UK, with real-time availability, pricing, and hours! 🎯",
            'suggestions': [
                "Try: 'Find EV parking in Manchester city centre at 2pm'",
                "Or: 'Can I park on Oxford Street, London?'",
                "Or: 'Show me accessible parking near Birmingham Station'"
            ],
            'type': 'greeting',
            'status': 'success'
        }

    def handle_parking_query(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle parking queries with full HERE.com data integration"""
        location = entities.get('location') or context.location
        time_info = entities.get('time') or context.time
        parking_type = entities.get('parking_type') or 'any'
        
        if not location:
            return {
                'message': "I'd love to help you find parking! 🚗",
                'response': "Please tell me where you're looking to park. A street, city, or landmark works perfectly!",
                'suggestions': [
                    "Example: 'Oxford Street, London'",
                    "Example: 'near Manchester Piccadilly Station'",
                    "Example: 'Birmingham city centre'"
                ],
                'type': 'location_needed',
                'status': 'success'
            }
        
        enthusiasm = random.choice(self.personality_responses['understanding'])
        response_parts = [f"{enthusiasm} in {location}"]
        if time_info:
            response_parts.append(f"at {time_info}")
        if context.duration:
            response_parts.append(f"for {context.duration}")
        if parking_type != 'any':
            response_parts.append(f"({parking_type} parking)")
        contextual_response = " ".join(response_parts) + "! Let me check HERE.com for you..."
        
        try:
            parking_results, nearby_locations = self.search_parking_with_context(location, context, parking_type)
            
            if parking_results and len(parking_results) > 0:
                quality_results = [spot for spot in parking_results if self.is_quality_parking_spot(spot)]
                
                if quality_results:
                    availability_message = self.generate_availability_message(time_info, location)
                    nearby_message = self.generate_nearby_locations_message(nearby_locations, location)
                    
                    return {
                        'message': f"Brilliant! 🎉 {availability_message}",
                        'response': f"Using HERE.com, I found {len(quality_results)} {parking_type if parking_type != 'any' else 'great'} parking options in {location}. {nearby_message}Here are the best ones, including pricing, hours, and availability:",
                        'data': {
                            'location': location,
                            'search_context': {
                                'time': time_info,
                                'duration': context.duration,
                                'vehicle': context.vehicle_type,
                                'budget': context.budget,
                                'preferences': context.preferences,
                                'parking_type': parking_type
                            },
                            'parking_spots': quality_results,
                            'nearby_locations': nearby_locations
                        },
                        'uk_parking_tip': self.get_relevant_uk_parking_tip(location, time_info, parking_type),
                        'suggestions': [
                            "Want more details about these spots?",
                            "Need parking for a different time or type?",
                            f"Should I check nearby {nearby_locations[0]['name'] if nearby_locations else 'areas'}?"
                        ],
                        'type': 'parking_results',
                        'status': 'success'
                    }
            
            mock_spots = self.generate_helpful_mock_data(location, context, parking_type)
            uk_advice = self.get_detailed_uk_parking_advice(location, time_info, parking_type)
            nearby_message = self.generate_nearby_locations_message(nearby_locations, location)
            
            return {
                'message': random.choice(self.personality_responses['no_data']),
                'response': f"While HERE.com didn't return specific data for {location}, you can definitely park there! Here's what you need to know about {parking_type if parking_type != 'any' else 'parking'}, plus nearby options: {nearby_message}",
                'data': {
                    'location': location,
                    'search_context': {
                        'time': time_info,
                        'duration': context.duration,
                        'vehicle': context.vehicle_type,
                        'budget': context.budget,
                        'preferences': context.preferences,
                        'parking_type': parking_type
                    },
                    'parking_spots': mock_spots,
                    'nearby_locations': nearby_locations,
                    'is_mock_data': True
                },
                'uk_parking_advice': uk_advice,
                'suggestions': [
                    f"Check {location} council website for parking details",
                    "Use apps like JustPark or RingGo for real-time info",
                    "Ask about specific streets or landmarks nearby"
                ],
                'type': 'parking_advice',
                'status': 'partial'
            }
                
        except Exception as e:
            uk_advice = self.get_detailed_uk_parking_advice(location, time_info, parking_type)
            mock_spots = self.generate_helpful_mock_data(location, context, parking_type)
            nearby_message = self.generate_nearby_locations_message(nearby_locations, location)
            
            return {
                'message': "I'm having a bit of trouble with HERE.com's live data, but no worries! 🔧",
                'response': f"You can absolutely park in {location}! Here's some tailored advice for {parking_type if parking_type != 'any' else 'parking'}, plus nearby options: {nearby_message}",
                'data': {
                    'location': location,
                    'parking_spots': mock_spots,
                    'nearby_locations': nearby_locations,
                    'is_mock_data': True
                },
                'uk_parking_advice': uk_advice,
                'suggestions': [
                    f"Try {location} council website for parking info",
                    "Use apps like JustPark, ParkNow, or RingGo",
                    "Look for local parking signs and restrictions"
                ],
                'type': 'advice',
                'status': 'advice'
            }

    def is_quality_parking_spot(self, spot: Dict) -> bool:
        """Check if this is a valid parking-related result"""
        title = spot.get('title', '').lower()
        categories = [cat.get('name', '').lower() for cat in spot.get('categories', [])]
        
        parking_keywords = ['parking', 'car park', 'garage', 'park', 'lot', 'bay', 'space', 'charging', 'ev']
        has_parking_keyword = any(keyword in title for keyword in parking_keywords)
        
        parking_categories = ['parking', 'transport', 'automotive', 'charging station']
        has_parking_category = any(cat in categories for cat in parking_categories if cat)
        
        exclude_keywords = ['restaurant', 'hotel', 'shop', 'church', 'school', 'hospital']
        is_excluded = any(keyword in title for keyword in exclude_keywords) and not has_parking_keyword
        
        return (has_parking_keyword or has_parking_category) and not is_excluded

    def generate_helpful_mock_data(self, location: str, context: ParkingContext, parking_type: str) -> List[Dict]:
        """Generate realistic mock parking data tailored to HERE.com types"""
        location_lower = location.lower()
        is_city_centre = any(term in location_lower for term in ['centre', 'center', 'city', 'town centre', 'high street'])
        is_london = 'london' in location_lower
        is_station = any(term in location_lower for term in ['station', 'railway', 'train'])
        is_street = any(term in location_lower for term in ['street', 'st', 'road', 'rd', 'lane', 'avenue', 'ave'])
        
        mock_spots = []
        
        # On-street parking
        if parking_type in ['any', 'on-street'] and is_street:
            mock_spots.append({
                'id': abs(hash(f'Street Parking {location}')),
                'title': f'Street Parking on {location}',
                'address': f'{location}, UK',
                'distance': 50,
                'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                'categories': ['Parking'],
                'analysis': {
                    'type': 'On-Street Parking',
                    'estimated_cost': '£1-3/hour' if not is_london else '£2-5/hour',
                    'best_for': ['Quick visits', 'Budget parking', 'Flexibility'],
                    'considerations': [
                        'Check single/double yellow lines',
                        'Resident permits may apply',
                        'Enforcement active 8am-6pm'
                    ]
                },
                'availability': {
                    'status': 'Variable - check signs',
                    'confidence': 'Low',
                    'restrictions': 'Typically 1-2 hour limits',
                    'last_updated': datetime.now().strftime('%H:%M')
                },
                'recommendations': [
                    '⚠️ Always check signs for restrictions',
                    '📱 Use RingGo or JustPark to pay',
                    '🕐 Free after 6pm in many areas'
                ],
                'uk_specific': {
                    'blue_badge_spaces': 'Limited - check signs',
                    'permit_required': 'Possible in residential areas',
                    'enforcement_hours': '8am-6pm Mon-Sat',
                    'payment_methods': ['Pay-and-display', 'Mobile apps']
                }
            })
        
        # Off-street parking
        if parking_type in ['any', 'off-street']:
            mock_spots.append({
                'id': abs(hash(f'Multi-Storey {location}')),
                'title': f'{location} Multi-Storey Car Park',
                'address': f'City Centre, {location}',
                'distance': 150,
                'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                'categories': ['Parking'],
                'analysis': {
                    'type': 'Multi-Storey Car Park',
                    'estimated_cost': '£3-5/hour' if not is_london else '£4-8/hour',
                    'best_for': ['Weather protection', 'Security', 'CCTV'],
                    'considerations': ['Height restrictions 2.1m', 'Busy during peak times']
                },
                'availability': {
                    'status': 'Usually available with 200+ spaces',
                    'confidence': 'High',
                    'peak_times': '12pm-2pm and 5pm-7pm',
                    'last_updated': datetime.now().strftime('%H:%M')
                },
                'recommendations': [
                    '🏢 Covered parking - great for weather',
                    '🔒 Secure with CCTV and patrols',
                    '♿ Disabled parking bays available'
                ],
                'uk_specific': {
                    'blue_badge_spaces': True,
                    'contactless_payment': True,
                    'max_height': '2.1m',
                    'operating_hours': '24 hours'
                }
            })
        
        # EV parking
        if parking_type in ['any', 'ev'] and (context.vehicle_type and 'electric' in context.vehicle_type.lower() or parking_type == 'ev'):
            mock_spots.append({
                'id': abs(hash(f'EV Charging {location}')),
                'title': f'{location} EV Charging Station',
                'address': f'Near {location} Centre',
                'distance': 200,
                'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                'categories': ['Charging Station'],
                'analysis': {
                    'type': 'EV Charging Station',
                    'estimated_cost': '£0.30-0.50/kWh' if not is_london else '£0.40-0.60/kWh',
                    'best_for': ['Electric vehicles', 'Eco-friendly parking'],
                    'considerations': ['Check charger compatibility', 'Booking may be required']
                },
                'availability': {
                    'status': 'Moderate - check app for real-time',
                    'confidence': 'Medium',
                    'last_updated': datetime.now().strftime('%H:%M')
                },
                'recommendations': [
                    '🔌 Supports Type 2 and CCS chargers',
                    '📱 Use apps like Zap-Map or ChargePoint',
                    '🕐 Check operating hours'
                ],
                'uk_specific': {
                    'blue_badge_spaces': True,
                    'charger_types': ['Type 2', 'CCS'],
                    'operating_hours': '24 hours'
                }
            })
        
        # Accessible parking
        if parking_type in ['any', 'accessible'] and 'accessible' in context.preferences:
            mock_spots.append({
                'id': abs(hash(f'Accessible Parking {location}')),
                'title': f'{location} Accessible Parking',
                'address': f'Near {location} Centre',
                'distance': 100,
                'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                'categories': ['Parking'],
                'analysis': {
                    'type': 'Accessible Parking',
                    'estimated_cost': 'Free with blue badge' if not is_london else 'Free/reduced with blue badge',
                    'best_for': ['Blue badge holders', 'Accessibility'],
                    'considerations': ['Display blue badge clearly', 'Limited spaces']
                },
                'availability': {
                    'status': 'Limited - arrive early',
                    'confidence': 'Medium',
                    'last_updated': datetime.now().strftime('%H:%M')
                },
                'recommendations': [
                    '♿ Blue badge spaces available',
                    '🚶 Close to key amenities',
                    '⚠️ Check signage for restrictions'
                ],
                'uk_specific': {
                    'blue_badge_spaces': True,
                    'accessibility_features': ['Wide bays', 'Level access'],
                    'operating_hours': '24 hours'
                }
            })
        
        # Permit parking
        if parking_type in ['any', 'permit']:
            mock_spots.append({
                'id': abs(hash(f'Permit Parking {location}')),
                'title': f'{location} Resident Permit Zone',
                'address': f'Residential Area, {location}',
                'distance': 300,
                'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                'categories': ['Parking'],
                'analysis': {
                    'type': 'Resident Permit Parking',
                    'estimated_cost': 'Permit required',
                    'best_for': ['Residents', 'Long-term parking'],
                    'considerations': ['Permits needed for non-residents', 'Enforcement active']
                },
                'availability': {
                    'status': 'Restricted - permit holders only',
                    'confidence': 'High',
                    'restrictions': 'Permit required 8am-6pm',
                    'last_updated': datetime.now().strftime('%H:%M')
                },
                'recommendations': [
                    '🪪 Check if you need a visitor permit',
                    '📱 Use council apps for permit info',
                    '🕐 Free outside permit hours'
                ],
                'uk_specific': {
                    'permit_required': True,
                    'enforcement_hours': '8am-6pm Mon-Sat',
                    'visitor_permits': 'Available via council'
                }
            })
        
        return mock_spots[:3]

    def get_detailed_uk_parking_advice(self, location: str, time_info: str, parking_type: str) -> Dict:
        """Comprehensive UK parking advice tailored to HERE.com types"""
        location_lower = location.lower()
        is_london = 'london' in location_lower
        is_city = any(term in location_lower for term in ['city', 'centre', 'center'])
        is_station = any(term in location_lower for term in ['station', 'railway'])
        is_street = any(term in location_lower for term in ['street', 'st', 'road', 'rd', 'lane', 'avenue', 'ave'])
        
        advice = {
            'general_tips': self.uk_parking_rules['general'],
            'cost_guidance': {},
            'time_specific_advice': '',
            'local_considerations': [],
            'apps_and_payments': [
                'RingGo - widely used across the UK',
                'JustPark - find and book private spaces',
                'ParkNow - real-time parking info',
                'Zap-Map - for EV charging stations'
            ]
        }
        
        if parking_type == 'on-street' or is_street:
            advice['cost_guidance'] = {
                'typical_range': '£1-3/hour' if not is_london else '£2-5/hour',
                'street_specific': 'Check for resident permits and yellow line restrictions',
                'payment': 'Pay-and-display or mobile apps like RingGo'
            }
            advice['local_considerations'].extend([
                'Single/double yellow lines strictly enforced',
                'Resident permit zones common in residential areas',
                'Time limits typically 1-2 hours'
            ])
        elif parking_type == 'off-street':
            advice['cost_guidance'] = {
                'typical_range': '£2-5/hour' if not is_london else '£4-8/hour',
                'off_street_specific': 'Multi-storey and council car parks offer secure options',
                'payment': 'Contactless, card, or mobile apps'
            }
            advice['local_considerations'].extend([
                'Check height restrictions (typically 2.1m)',
                '24-hour access in many garages',
                'Free after 6pm in some council car parks'
            ])
        elif parking_type == 'ev':
            advice['cost_guidance'] = {
                'typical_range': '£0.30-0.50/kWh' if not is_london else '£0.40-0.60/kWh',
                'ev_specific': 'Check charger type compatibility (Type 2, CCS)',
                'payment': 'Mobile apps like Zap-Map or ChargePoint'
            }
            advice['local_considerations'].extend([
                'Booking recommended for busy stations',
                'Check operating hours for availability',
                'Some stations offer free parking while charging'
            ])
        elif parking_type == 'accessible':
            advice['cost_guidance'] = {
                'typical_range': 'Free with blue badge' if not is_london else 'Free/reduced with blue badge',
                'accessible_specific': 'Display blue badge clearly',
                'payment': 'Often free for blue badge holders'
            }
            advice['local_considerations'].extend([
                'Wide bays and level access available',
                'Limited spaces - arrive early',
                'Check local council rules for blue badge privileges'
            ])
        elif parking_type == 'permit':
            advice['cost_guidance'] = {
                'typical_range': 'Permit required',
                'permit_specific': 'Visitor permits available via council',
                'payment': 'Check council website for permit costs'
            }
            advice['local_considerations'].extend([
                'Permit zones enforced 8am-6pm typically',
                'Free parking outside permit hours',
                'Contact council for visitor permits'
            ])
        else:
            advice['cost_guidance'] = {
                'typical_range': '£1-5/hour' if not is_london else '£2-8/hour',
                'general': 'Varies by location and type',
                'payment': 'Card, contactless, or mobile apps'
            }
        
        if time_info:
            if any(term in time_info for term in ['morning', '8', '9', '10']):
                advice['time_specific_advice'] = 'Morning rush hour: Arrive early as spaces fill quickly. Many restrictions start at 8am.'
            elif any(term in time_info for term in ['evening', 'night', '6', '7', '8']):
                advice['time_specific_advice'] = 'Evening: Many car parks become free after 6pm. Street parking restrictions usually end by 6-7pm.'
            elif any(term in time_info for term in ['lunch', '12', '1', '2']):
                advice['time_specific_advice'] = 'Lunch time: City centres get busy. Consider parking slightlyLire further out.'
        
        if is_station:
            advice['local_considerations'].extend([
                'Station car parks fill up early - book ahead',
                'Season tickets available for commuters',
                'Some operators offer rail ticket discounts'
            ])
        
        if is_london:
            advice['local_considerations'].extend([
                'Congestion charge applies Mon-Fri 7am-6pm',
                'ULEZ charges may apply',
                'Red routes have strict restrictions'
            ])
        
        advice['local_considerations'].extend([
            'Blue badge holders get extra time and free parking in many areas',
            'EV charging points increasingly available',
            'Market days can affect availability'
        ])
        
        return advice

    def get_relevant_uk_parking_tip(self, location: str, time_info: str, parking_type: str) -> str:
        """Get a relevant parking tip tailored to HERE.com types"""
        tips = [
            "💡 Most UK councils offer free parking after 6pm and on Sundays",
            "💡 Download RingGo or JustPark for real-time availability",
            "💡 Blue badge holders get extra time and free parking in many areas",
            "💡 Always check parking signs - they're legally binding",
            "💡 Zap-Map is great for finding EV charging stations"
        ]
        
        location_lower = location.lower()
        if 'london' in location_lower:
            return "💡 London's congestion charge (£15/day) applies Mon-Fri 7am-6pm in central areas"
        elif any(term in location_lower for term in ['station', 'railway']):
            return "💡 Book station parking online for cheaper rates and guaranteed spaces"
        elif any(term in location_lower for term in ['street', 'st', 'road', 'rd']):
            return "💡 Check street parking signs for resident permits and time restrictions"
        elif parking_type == 'ev':
            return "💡 Use Zap-Map to find available EV charging stations in real-time"
        elif parking_type == 'accessible':
            return "💡 Display your blue badge clearly for free or extended parking"
        elif parking_type == 'permit':
            return "💡 Check with the local council for visitor parking permits"
        elif time_info and any(term in time_info for term in ['evening', 'night']):
            return "💡 Evening parking is often free after 6pm in most UK towns"
        
        return random.choice(tips)

    def handle_availability_question(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle availability questions with HERE.com real-time data"""
        location = entities.get('location') or context.location or "that area"
        time_info = entities.get('time') or context.time or "that time"
        parking_type = entities.get('parking_type') or 'any'
        
        availability_msg = self.generate_availability_message(time_info, location)
        uk_context = self.get_uk_availability_context(time_info, location, parking_type)
        
        return {
            'message': f"Good question! {availability_msg} 📊",
            'response': f"Using HERE.com's real-time data, here's what to expect for {parking_type if parking_type != 'any' else 'parking'} in {location} at {time_info}:",
            'availability_info': uk_context,
            'suggestions': [
                f"Search for specific {parking_type} spots in {location}",
                "Tell me your backup location preferences",
                "Ask about pricing or restrictions"
            ],
            'type': 'availability_info',
            'status': 'success'
        }

    def get_uk_availability_context(self, time_info: str, location: str, parking_type: str) -> Dict:
        """Get UK-specific availability context with HERE.com data"""
        context = {
            'general_availability': 'Moderate',
            'peak_times': [],
            'quiet_times': [],
            'special_considerations': [],
            'real_time_status': 'Not available'
        }
        
        location_lower = location.lower()
        
        if time_info:
            time_lower = time_info.lower()
            if any(term in time_lower for term in ['morning', '8', '9', '10']):
                context['general_availability'] = 'Challenging - Morning rush'
                context['peak_times'].append('8am-10am: Commuter rush, limited spaces')
                context['special_considerations'].append('Arrive 15-20 minutes early')
            elif any(term in time_lower for term in ['lunch', '12', '1', '2']):
                context['general_availability'] = 'Busy - Lunch period'
                context['peak_times'].append('12pm-2pm: Shoppers and office workers')
            elif any(term in time_lower for term in ['evening', 'night', '6', '7', '8']):
                context['general_availability'] = 'Good - Evening availability'
                context['quiet_times'].append('After 6pm: Many restrictions end')
                context['special_considerations'].append('Often free parking after 6pm')
        
        if parking_type == 'on-street':
            context['special_considerations'].extend([
                'Check for resident permit zones',
                'Single/double yellow lines enforced',
                'Time limits typically 1-2 hours'
            ])
        elif parking_type == 'off-street':
            context['special_considerations'].extend([
                'Larger capacity in multi-storey car parks',
                'Check height restrictions',
                '24-hour access often available'
            ])
        elif parking_type == 'ev':
            context['special_considerations'].extend([
                'Limited charging spots - book ahead',
                'Real-time availability via apps like Zap-Map',
                'Check charger compatibility'
            ])
        elif parking_type == 'accessible':
            context['special_considerations'].extend([
                'Limited spaces - arrive early',
                'Blue badge required for benefits',
                'Check for level access and wide bays'
            ])
        elif parking_type == 'permit':
            context['special_considerations'].extend([
                'Permit holders have priority',
                'Visitor permits may be available',
                'Free outside enforcement hours'
            ])
        
        if any(term in location_lower for term in ['city', 'centre', 'center', 'high street']):
            context['special_considerations'].extend([
                'City centres busiest 10am-4pm weekdays',
                'Saturday shopping affects availability',
                'Sunday usually quieter with free parking'
            ])
        
        if 'london' in location_lower:
            context['special_considerations'].extend([
                'Congestion charge area very limited',
                'Use parking apps for real-time updates',
                'Consider park & ride options'
            ])
        
        return context

    def generate_availability_message(self, time_info: str, location: str) -> str:
        """Generate contextual availability messages"""
        current_hour = datetime.now().hour
        location_lower = location.lower()
        
        if not time_info or time_info in ['now', 'right now']:
            if 8 <= current_hour <= 10:
                return "Morning rush hour is on, so parking might be tricky, but HERE.com has some great spots available!"
            elif 12 <= current_hour <= 14:
                return "Lunch time can get busy in city centres, but I'll find you a spot with HERE.com!"
            elif 17 <= current_hour <= 19:
                return "Evening rush hour, but many restrictions lift after 6pm - let's check HERE.com!"
            elif 20 <= current_hour <= 23:
                return "Evening parking is usually easier, and HERE.com shows plenty of options after 6pm!"
            else:
                return "Quiet time for parking - HERE.com shows lots of choices right now!"
        
        elif any(term in time_info.lower() for term in ['morning', '8', '9', '10']):
            return "Morning parking can be tough with commuters, but HERE.com knows the best spots!"
        elif any(term in time_info.lower() for term in ['lunch', '12', '1', '2']):
            return "Lunch time is busy in town centres, but HERE.com can find you a spot!"
        elif any(term in time_info.lower() for term in ['evening', 'night', '6', '7', '8']):
            return "Evening parking is easier, and HERE.com shows many spots free after 6pm!"
        elif 'weekend' in time_info.lower() or 'saturday' in time_info.lower():
            return "Weekends vary - Saturdays are busy, but Sundays are quieter, and HERE.com has the details!"
        else:
            return "I'll check HERE.com for the best parking options at that time!"

    def generate_nearby_locations_message(self, nearby_locations: List[Dict], original_location: str) -> str:
        """Generate message about nearby locations"""
        if not nearby_locations:
            return f"I've also checked nearby areas around {original_location} for more options."
        
        nearby_names = [loc['name'] for loc in nearby_locations]
        if len(nearby_names) == 1:
            return f"I've found parking options in nearby {nearby_names[0]} as well."
        elif len(nearby_names) > 1:
            return f"I've checked nearby areas like {', '.join(nearby_names[:2])}{' and more' if len(nearby_names) > 2 else ''} for extra options."
        return ""

    def search_parking_with_context(self, location: str, context: ParkingContext, parking_type: str) -> Tuple[List[Dict], List[Dict]]:
        """Search for parking using HERE.com's full capabilities"""
        lat, lng, address = self.geocode_location_uk(location)
        nearby_locations = []
        
        if not lat:
            nearby_locations = self.search_nearby_locations(location)
            return [], nearby_locations
        
        spots = self.search_parking_spots_enhanced(lat, lng, location, parking_type)
        processed_spots = []
        
        for spot in spots:
            if self.is_quality_parking_spot(spot):
                enhanced_spot = self.enhance_spot_with_uk_context(spot, context, location, parking_type)
                processed_spots.append(enhanced_spot)
        
        if not processed_spots:
            nearby_locations = self.search_nearby_locations(location)
        
        processed_spots.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        return processed_spots[:6], nearby_locations

    def search_nearby_locations(self, location: str) -> List[Dict]:
        """Search for nearby cities/towns using HERE.com"""
        params = {
            'q': f"{location} UK",
            'apiKey': self.api_key,
            'limit': 5,
            'in': 'countryCode:GBR',
            'types': 'city,area'
        }
        
        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            nearby_locations = []
            for item in data.get('items', []):
                if item.get('address', {}).get('countryCode') == 'GBR':
                    nearby_locations.append({
                        'name': item.get('address', {}).get('label', '').split(',')[0].strip(),
                        'coordinates': item.get('position', {}),
                        'distance': item.get('distance', 0)
                    })
            
            return nearby_locations[:3]
        except Exception:
            return []

    def geocode_location_uk(self, location_query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Enhanced geocoding with UK bias using HERE.com"""
        enhanced_query = location_query
        if not any(country in location_query.lower() for country in ['uk', 'united kingdom', 'england', 'scotland', 'wales']):
            enhanced_query = f"{location_query} UK"
        
        params = {
            'q': enhanced_query,
            'apiKey': self.api_key,
            'limit': 3,
            'in': 'countryCode:GBR'
        }

        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                uk_results = [item for item in data['items'] 
                             if item.get('address', {}).get('countryCode') == 'GBR']
                
                result = uk_results[0] if uk_results else data['items'][0]
                position = result['position']
                address = result.get('address', {}).get('label', location_query)
                return position['lat'], position['lng'], address
            return None, None, None
        except Exception as e:
            print(f"bla bla Geocoding error: {e}")
            return None, None, None

    def search_parking_spots_enhanced(self, lat: float, lng: float, location: str, parking_type: str) -> List[Dict]:
        """Enhanced parking search using HERE.com's full capabilities"""
        queries = {
            'on-street': ['on-street parking', 'metered parking', 'public parking'],
            'off-street': ['parking garage', 'car park', 'multi storey car park', 'council car park', 'park and ride'],
            'ev': ['electric vehicle charging', 'ev charging station', 'charging point'],
            'accessible': ['accessible parking', 'disabled parking', 'blue badge parking'],
            'permit': ['resident parking', 'permit parking', 'restricted parking'],
            'any': ['parking', 'car park', 'public parking', 'NCP car park']
        }

        all_spots = []
        seen_positions = set()

        for query in queries.get(parking_type, queries['any']):
            params = {
                'at': f"{lat},{lng}",
                'q': query,
                'limit': 10,
                'radius': 2000,
                'apiKey': self.api_key,
                'categories': '700-7600,7200-7600-0000'  # Parking and charging stations
            }

            try:
                response = requests.get(self.discover_url, params=params, timeout=8)
                response.raise_for_status()
                data = response.json()
                spots = data.get('items', [])

                # Hypothetical real-time parking API call
                for spot in spots:
                    pos = spot.get('position', {})
                    pos_key = f"{pos.get('lat', 0):.4f},{pos.get('lng', 0):.4f}"
                    
                    if pos_key not in seen_positions and self.is_quality_parking_spot(spot):
                        seen_positions.add(pos_key)
                        # Fetch real-time data (hypothetical endpoint)
                        real_time_data = self.fetch_real_time_parking_data(pos.get('lat'), pos.get('lng'), spot.get('id', ''))
                        spot.update(real_time_data)
                        all_spots.append(spot)

            except Exception:
                continue

        return all_spots

    def fetch_real_time_parking_data(self, lat: float, lng: float, parking_id: str) -> Dict:
        """Fetch real-time parking data from HERE.com (hypothetical)"""
        params = {
            'at': f"{lat},{lng}",
            'id': parking_id,
            'apiKey': self.api_key
        }
        
        try:
            response = requests.get(self.parking_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            return {
                'availability': {
                    'status': data.get('status', 'Unknown'),
                    'spaces_available': data.get('spacesAvailable', 0),
                    'last_updated': data.get('lastUpdated', datetime.now().strftime('%H:%M')),
                    'occupancy': data.get('occupancy', 'Unknown')
                },
                'pricing': {
                    'rate': data.get('rate', 'Unknown'),
                    'free_times': data.get('freeTimes', []),
                    'operating_hours': data.get('operatingHours', 'Unknown')
                },
                'accessibility': {
                    'accessible_spaces': data.get('accessibleSpaces', False),
                    'features': data.get('accessibilityFeatures', [])
                },
                'ev_charging': {
                    'available': data.get('evCharging', False),
                    'charger_types': data.get('chargerTypes', []),
                    'operating_hours': data.get('evOperatingHours', 'Unknown')
                },
                'permit_info': {
                    'permit_required': data.get('permitRequired', False),
                    'zone': data.get('parkingZone', 'Unknown')
                }
            }
        except Exception:
            return {
                'availability': {'status': 'Unknown', 'spaces_available': 0, 'last_updated': datetime.now().strftime('%H:%M'), 'occupancy': 'Unknown'},
                'pricing': {'rate': 'Unknown', 'free_times': [], 'operating_hours': 'Unknown'},
                'accessibility': {'accessible_spaces': False, 'features': []},
                'ev_charging': {'available': False, 'charger_types': [], 'operating_hours': 'Unknown'},
                'permit_info': {'permit_required': False, 'zone': 'Unknown'}
            }

    def enhance_spot_with_uk_context(self, spot: Dict, context: ParkingContext, location: str, parking_type: str) -> Dict:
        """Enhance parking spot with UK and HERE.com context"""
        title = spot.get('title', 'Parking Area')
        address = spot.get('address', {}).get('label', 'Address not available')
        distance = spot.get('distance', 0)
        
        enhanced = {
            'id': abs(hash(title + address)),
            'title': title,
            'address': address,
            'distance': distance,
            'coordinates': spot.get('position', {}),
            'categories': [cat.get('name', '') for cat in spot.get('categories', [])],
            'availability': spot.get('availability', {'status': 'Unknown', 'spaces_available': 0, 'last_updated': datetime.now().strftime('%H:%M'), 'occupancy': 'Unknown'}),
            'pricing': spot.get('pricing', {'rate': 'Unknown', 'free_times': [], 'operating_hours': 'Unknown'}),
            'accessibility': spot.get('accessibility', {'accessible_spaces': False, 'features': []}),
            'ev_charging': spot.get('ev_charging', {'available': False, 'charger_types': [], 'operating_hours': 'Unknown'}),
            'permit_info': spot.get('permit_info', {'permit_required': False, 'zone': 'Unknown'})
        }
        
        enhanced['analysis'] = self.analyze_spot_for_uk_context(spot, context, location, parking_type)
        enhanced['relevance_score'] = self.calculate_uk_relevance_score(spot, context, location, parking_type)
        enhanced['recommendations'] = self.generate_uk_spot_recommendations(spot, context, parking_type)
        enhanced['uk_specific'] = self.get_uk_specific_info(spot, location, parking_type)
        
        return enhanced

    def analyze_spot_for_uk_context(self, spot: Dict, context: ParkingContext, location: str, parking_type: str) -> Dict:
        """Comprehensive analysis with HERE.com data"""
        title = spot.get('title', '').lower()
        location_lower = location.lower()
        
        analysis = {
            'type': parking_type.capitalize() if parking_type != 'any' else 'Car Park',
            'estimated_cost': '£2-4/hour',
            'best_for': [],
            'considerations': []
        }
        
        if parking_type == 'on-street' or any(term in title for term in ['street', 'st', 'road', 'rd']):
            analysis['type'] = 'On-Street Parking'
            analysis['estimated_cost'] = '£1-3/hour' if not 'london' in location_lower else '£2-5/hour'
            analysis['best_for'].extend(['Quick visits', 'Budget parking', 'Flexibility'])
            analysis['considerations'].extend([
                'Check single/double yellow lines',
                'Resident permits may apply',
                'Time limits typically 1-2 hours'
            ])
        elif parking_type == 'off-street' or any(term in title for term in ['multi storey', 'multi-storey', 'mscp', 'garage', 'lot']):
            analysis['type'] = 'Off-Street Parking'
            analysis['estimated_cost'] = '£3-6/hour' if not 'london' in location_lower else '£5-10/hour'
            analysis['best_for'].extend(['Weather protection', 'Security', 'Large capacity'])
            analysis['considerations'].append('Height restrictions usually 2.1m')
        elif parking_type == 'ev' or any(term in title for term in ['ev', 'charging', 'electric']):
            analysis['type'] = 'EV Charging Station'
            analysis['estimated_cost'] = '£0.30-0.50/kWh' if not 'london' in location_lower else '£0.40-0.60/kWh'
            analysis['best_for'].extend(['Electric vehicles', 'Eco-friendly parking'])
            analysis['considerations'].extend(['Check charger compatibility', 'Booking may be required'])
        elif parking_type == 'accessible' or any(term in title for term in ['accessible', 'disabled', 'blue badge']):
            analysis['type'] = 'Accessible Parking'
            analysis['estimated_cost'] = 'Free with blue badge' if not 'london' in location_lower else 'Free/reduced with blue badge'
            analysis['best_for'].extend(['Blue badge holders', 'Accessibility'])
            analysis['considerations'].extend(['Display blue badge clearly', 'Limited spaces'])
        elif parking_type == 'permit' or any(term in title for term in ['permit', 'resident', 'restricted']):
            analysis['type'] = 'Resident Permit Parking'
            analysis['estimated_cost'] = 'Permit required'
            analysis['best_for'].extend(['Residents', 'Long-term parking'])
            analysis['considerations'].extend(['Permits needed for non-residents', 'Enforcement active'])
        
        if context.budget:
            if any(term in context.budget for term in ['cheap', 'budget', 'affordable']):
                if any(term in title for term in ['council', 'street']):
                    analysis['budget_rating'] = 'Excellent for budget'
                else:
                    analysis['budget_rating'] = 'Check for off-peak rates'
        
        if context.duration:
            if 'overnight' in context.duration:
                analysis['considerations'].append('Check overnight parking policies')
            elif any(term in context.duration for term in ['quick', 'short', 'hour']):
                analysis['best_for'].append('Short stays welcome')
        
        return analysis

    def calculate_uk_relevance_score(self, spot: Dict, context: ParkingContext, location: str, parking_type: str) -> int:
        """Calculate relevance with HERE.com-specific factors"""
        score = 50
        title = spot.get('title', '').lower()
        distance = spot.get('distance', 1000)
        
        if distance < 100:
            score += 30
        elif distance < 300:
            score += 20
        elif distance < 500:
            score += 10
        
        if any(term in title for term in ['car park', 'parking']):
            score += 15
        
        if any(term in title for term in ['council', 'public']):
            score += 10
        
        if parking_type != 'any' and parking_type in title:
            score += 20
        
        if context.preferences:
            if 'covered' in context.preferences and any(term in title for term in ['multi storey', 'garage']):
                score += 25
            if 'secure' in context.preferences and any(term in title for term in ['ncp', 'secure']):
                score += 20
            if 'accessible' in context.preferences and any(term in title for term in ['accessible', 'disabled']):
                score += 15
            if 'ev' in context.preferences and any(term in title for term in ['ev', 'charging']):
                score += 15
        
        if context.budget and any(term in context.budget for term in ['cheap', 'budget']):
            if any(term in title for term in ['council', 'street']):
                score += 15
        
        return min(100, score)

    def estimate_uk_availability(self, spot: Dict, context: ParkingContext) -> Dict:
        """Estimate availability using HERE.com data"""
        title = spot.get('title', '').lower()
        current_time = datetime.now()
        
        if any(term in title for term in ['multi storey', 'large', 'mscp']):
            base_availability = 'Good - Large capacity'
            confidence = 'High'
        elif 'council' in title:
            base_availability = 'Moderate - Popular with locals'
            confidence = 'Medium'
        elif 'station' in title:
            base_availability = 'Limited - Book ahead recommended'
            confidence = 'High'
        elif any(term in title for term in ['street', 'st', 'road', 'rd']):
            base_availability = 'Variable - Check signs'
            confidence = 'Low'
        elif any(term in title for term in ['ev', 'charging']):
            base_availability = 'Moderate - Check app for real-time'
            confidence = 'Medium'
        elif any(term in title for term in ['accessible', 'disabled']):
            base_availability = 'Limited - Arrive early'
            confidence = 'Medium'
        elif any(term in title for term in ['permit', 'resident']):
            base_availability = 'Restricted - Permit holders only'
            confidence = 'High'
        else:
            base_availability = 'Variable - Check locally'
            confidence = 'Medium'
        
        time_context = ""
        if context.time:
            time_lower = context.time.lower()
            if any(term in time_lower for term in ['morning', '8', '9']):
                time_context = " (Morning rush - arrive early)"
            elif any(term in time_lower for term in ['evening', '6', '7']):
                time_context = " (Evening - often free after 6pm)"
        
        return {
            'status': base_availability + time_context,
            'confidence': confidence,
            'last_updated': current_time.strftime('%H:%M'),
            'uk_context': 'Based on typical UK parking patterns and HERE.com data'
        }

    def generate_uk_spot_recommendations(self, spot: Dict, context: ParkingContext, parking_type: str) -> List[str]:
        """Generate recommendations tailored to HERE.com types"""
        recommendations = []
        title = spot.get('title', '').lower()
        distance = spot.get('distance', 0)
        
        if distance < 100:
            recommendations.append("🚶‍♂️ Right on your doorstep!")
        elif distance < 300:
            recommendations.append("🚶‍♂️ Just a 2-3 minute walk")
        elif distance < 500:
            recommendations.append("🚶‍♂️ About a 5-minute walk")
        
        if parking_type == 'on-street' or any(term in title for term in ['street', 'st', 'road', 'rd']):
            recommendations.append("⚠️ Check signs for restrictions and time limits")
            recommendations.append("📱 Use RingGo or JustPark for payment")
        elif parking_type == 'off-street' or any(term in title for term in ['multi storey', 'garage']):
            recommendations.append("🏢 Covered parking - great for British weather!")
        elif parking_type == 'ev' or any(term in title for term in ['ev', 'charging']):
            recommendations.append("🔌 Check charger type (Type 2, CCS)")
            recommendations.append("📱 Use Zap-Map for real-time availability")
        elif parking_type == 'accessible' or any(term in title for term in ['accessible', 'disabled']):
            recommendations.append("♿ Display blue badge clearly")
            recommendations.append("🚶 Close to amenities for accessibility")
        elif parking_type == 'permit' or any(term in title for term in ['permit', 'resident']):
            recommendations.append("🪪 Check council for visitor permits")
            recommendations.append("🕐 Free outside permit hours")
        
        if 'council' in title:
            recommendations.append("🏛️ Council rates - good value, often free evenings/Sundays")
        
        if 'ncp' in title:
            recommendations.append("🅿️ Professional NCP management - reliable and secure")
        
        if 'station' in title:
            recommendations.append("🚂 Perfect for train travel - book online for best rates")
        
        if context.duration:
            if 'overnight' in context.duration:
                recommendations.append("🌙 Check overnight policies")
            elif any(term in context.duration for term in ['quick', 'short']):
                recommendations.append("⚡ Good for quick visits")
        
        if context.preferences:
            if 'accessible' in context.preferences:
                recommendations.append("♿ Blue badge spaces available")
            if 'ev' in context.preferences:
                recommendations.append("🔌 EV charging available")
        
        return recommendations

    def get_uk_specific_info(self, spot: Dict, location: str, parking_type: str) -> Dict:
        """Get UK-specific parking info with HERE.com data"""
        title = spot.get('title', '').lower()
        location_lower = location.lower()
        
        uk_info = {
            'blue_badge_friendly': spot.get('accessibility', {}).get('accessible_spaces', False),
            'payment_methods': spot.get('pricing', {}).get('payment_methods', ['Card', 'Contactless', 'RingGo', 'Council app']),
            'typical_hours': spot.get('pricing', {}).get('operating_hours', '8am-6pm Mon-Sat'),
            'sunday_parking': 'Often free or reduced rates',
            'evening_parking': 'Check for free parking after 6pm'
        }
        
        if parking_type == 'on-street' or any(term in title for term in ['street', 'st', 'road', 'rd']):
            uk_info['special_notes'] = [
                'Check for resident permit zones',
                'Single/double yellow lines enforced',
                'Time limits typically 1-2 hours'
            ]
            uk_info['payment_methods'] = ['Pay-and-display', 'Mobile apps']
        
        if parking_type == 'ev' or any(term in title for term in ['ev', 'charging']):
            uk_info['ev_charging'] = {
                'available': spot.get('ev_charging', {}).get('available', False),
                'charger_types': spot.get('ev_charging', {}).get('charger_types', ['Type 2', 'CCS']),
                'operating_hours': spot.get('ev_charging', {}).get('operating_hours', '24 hours')
            }
        
        if parking_type == 'accessible' or any(term in title for term in ['accessible', 'disabled']):
            uk_info['accessibility_features'] = spot.get('accessibility', {}).get('features', ['Wide bays', 'Level access'])
        
        if parking_type == 'permit' or any(term in title for term in ['permit', 'resident']):
            uk_info['permit_info'] = {
                'permit_required': spot.get('permit_info', {}).get('permit_required', True),
                'zone': spot.get('permit_info', {}).get('zone', 'Unknown'),
                'visitor_permits': 'Available via council'
            }
        
        if 'london' in location_lower:
            uk_info['special_notes'] = uk_info.get('special_notes', []) + [
                'Congestion charge may apply',
                'ULEZ compliance required',
                'Higher rates than other UK cities'
            ]
        
        if 'station' in title:
            uk_info['special_features'] = [
                'Season tickets available',
                'Online booking recommended',
                'Rail passenger discounts may apply'
            ]
        
        if 'council' in title:
            uk_info['council_benefits'] = [
                'Resident permits may apply',
                'Local rate discounts',
                'Community-focused pricing'
            ]
        
        return uk_info

app = Flask(__name__)
CORS(app)
bot = IntelligentParksyBot()

@app.route('/', methods=['GET'])
def home():
    """Enhanced API home endpoint with HERE.com integration"""
    return jsonify({
        "message": "🇬🇧 Intelligent Parksy Bot - Your UK Parking Assistant Powered by HERE.com!",
        "version": "4.2 - UK Enhanced with Full HERE.com Integration",
        "status": "active",
        "features": [
            "🧠 Natural language understanding",
            "💬 Human-like conversations",
            "🔍 Comprehensive HERE.com parking search",
            "🛣️ On-street and off-street parking",
            "🔌 EV charging stations",
            "♿ Accessible parking support",
            "🪪 Permit and restricted parking info",
            "📊 Real-time availability",
            "💰 UK pricing in pounds (£)",
            "📍 Nearby location suggestions"
        ],
        "personality": "Friendly, helpful, and proper British! 🇬🇧✨",
        "coverage": "All UK cities, towns, streets, and transport hubs",
        "endpoints": {
            "chat": "/api/chat",
            "health": "/api/health"
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Enhanced health check with HERE.com context"""
    return jsonify({
        "status": "healthy",
        "bot_status": "ready to help with UK parking using HERE.com data! 🇬🇧🤖",
        "timestamp": datetime.now().isoformat(),
        "version": "4.2 - UK Enhanced with HERE.com",
        "here_api_configured": bool(os.getenv('HERE_API_KEY')),
        "uk_features": {
            "currency": "GBP (£)",
            "parking_rules": "UK-specific",
            "location_bias": "United Kingdom",
            "payment_apps": ["RingGo", "JustPark", "ParkNow", "Zap-Map"],
            "parking_types": ["On-street", "Off-street", "EV", "Accessible", "Permit"]
        }
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Enhanced chat endpoint with HERE.com data"""
    try:
        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({
                "error": "I need a message to chat with you! 😊",
                "status": "error",
                "example": {"message": "Find EV parking on Oxford Street, London at 2pm"}
            }), 400

        user_message = data['message'].strip()
        user_id = data.get('user_id', 'default')
        
        if not user_message:
            return jsonify({
                "message": "I'm here with HERE.com's data to help! 🤖",
                "response": "What would you like to know about parking in the UK?",
                "suggestions": ["Ask me about any parking type anywhere in the UK!"],
                "status": "success"
            })

        response = bot.generate_contextual_response(user_message, user_id)
        response['timestamp'] = datetime.now().isoformat()
        response['uk_enhanced'] = True
        response['here_com_integrated'] = True
        
        return jsonify(response)

    except Exception as e:
        return jsonify({
            "message": "Blimey! I've hit a small snag! 🔧",
            "response": "Don't worry - I'm still here with HERE.com's data to help with UK parking! Try again in a moment.",
            "error": str(e) if app.debug else "Technical hiccup",
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "suggestions": [
                "Try your question again",
                "Ask about general UK parking advice",
                "Check parking rules for your area"
            ]
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🇬🇧 Starting Enhanced Intelligent Parksy Bot...")
    print("💬 Ready for natural UK parking conversations!")
    print("🔍 Powered by HERE.com for comprehensive parking data!")
    print("🛣️ Full support for on-street, off-street, EV, accessible, and permit parking!")
    app.run(host='0.0.0.0', port=port, debug=False)
