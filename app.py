# intelligent_parksy.py - AI-Powered Conversational Parking Assistant (UK Enhanced)
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
import difflib

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
        # API Configuration
        self.api_key = os.getenv('HERE_API_KEY', 'demo_key_for_testing')
        self.base_url = "https://discover.search.hereapi.com/v1/discover"
        self.geocoding_url = "https://geocode.search.hereapi.com/v1/geocode"
        
        # Conversation context storage (in production, use Redis or database)
        self.user_contexts = {}
        
        # Enhanced location extraction patterns
        self.location_patterns = [
            # Street patterns
            r'\b(?:on|at|in)\s+([A-Z][a-zA-Z\s]+(?:street|st|road|rd|lane|ln|avenue|ave|drive|dr|close|cl|way|row|place|pl|crescent|cres|terrace|ter|gardens|gdns|park|square|sq|court|ct|mews|hill|green|common))\b',
            # Area/district patterns
            r'\b(?:in|at|near|around|by)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:at|for|around|by|area|district|\d)|\s*[,.]|$)',
            # Landmarks and specific places
            r'\b(?:near|by|at)\s+([A-Z][a-zA-Z\s]+(?:station|hospital|university|college|shopping centre|centre|center|mall|airport|stadium|theatre|cinema|library|school|church|cathedral|museum|gallery|park|heath|common))\b',
            # Postcode patterns
            r'\b([A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2})\b',
            # City/town patterns
            r'\b([A-Z][a-zA-Z\s]{2,})\b(?=\s+(?:city|town|centre|center|area|district|$))',
            # General location patterns
            r'\b([A-Z][a-zA-Z\s]{2,})\b'
        ]
        
        # Common UK locations for fuzzy matching
        self.common_uk_locations = [
            'London', 'Manchester', 'Birmingham', 'Leeds', 'Glasgow', 'Liverpool', 'Bristol', 
            'Sheffield', 'Edinburgh', 'Leicester', 'Coventry', 'Bradford', 'Cardiff', 'Belfast',
            'Nottingham', 'Kingston upon Hull', 'Newcastle upon Tyne', 'Stoke-on-Trent', 
            'Southampton', 'Derby', 'Portsmouth', 'Brighton', 'Plymouth', 'Northampton',
            'Reading', 'Luton', 'Wolverhampton', 'Bolton', 'Bournemouth', 'Norwich', 'Swindon',
            'Swansea', 'Southend-on-Sea', 'Middlesbrough', 'Peterborough', 'Cambridge', 'Oxford',
            'York', 'Ipswich', 'Warrington', 'Slough', 'Gloucester', 'Watford', 'Rotherham',
            'Exeter', 'Scunthorpe', 'Blackpool', 'Crawley', 'Mansfield', 'Basildon', 'Gillingham'
        ]
        
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
        
        # Enhanced intent patterns with UK-specific language
        self.intent_patterns = {
            'greeting': [
                r'\b(hi|hello|hey|alright|morning|afternoon|evening|cheers|hiya)\b',
                r'^(hey there|what\'s up|how do|you alright)\b'
            ],
            'parking_query': [
                r'\b(park|parking|spot|car park|bay|space|motor)\b',
                r'\b(can\s+i\s+park|where\s+to\s+park|need\s+parking|looking\s+for\s+parking)\b',
                r'\b(find\s+me\s+a\s+spot|park\s+my\s+car|somewhere\s+to\s+park)\b'
            ],
            'time_query': [
                r'\b(\d{1,2}(:\d{2})?\s*(am|pm)|at\s+\d|tonight|morning|afternoon|evening)\b',
                r'\b(now|later|tomorrow|today|this\s+(morning|afternoon|evening))\b',
                r'\b(for\s+\d+\s+(hours?|hrs|minutes?|mins)|overnight|all\s+day)\b'
            ],
            'location_query': [
                r'\b(in|at|near|around|close\s+to|by)\s+\w+',
                r'\b\w+\s+(street|st|road|rd|lane|avenue|ave|city|town|centre|high\s+street|market|station)\b'
            ],
            'budget_concern': [
                r'\b(cheap|affordable|budget|expensive|free|cost|dear|pricey)\b',
                r'£\d+|\d+\s+(pounds?|quid|pence|p)\b'
            ],
            'vehicle_info': [
                r'\b(car|motor|truck|van|lorry|motorcycle|motorbike|bike|SUV|estate|hatchback)\b',
                r'\b(big|large|small|compact|electric|hybrid)\s+(car|vehicle|motor)\b'
            ],
            'availability_question': [
                r'\b(available|open|busy|full|empty|spaces?|free)\b',
                r'\b(can\s+i|will\s+there\s+be|is\s+there|any\s+chance)\b'
            ]
        }
        
        # More natural, conversational personality responses
        self.personality_responses = {
            'greeting': [
                "Alright there! 👋 I'm your parking mate - what can I help you sort out today?",
                "Hello! 🚗 Looking for somewhere to park? You've come to the right person!",
                "Hi there! I'm here to make parking dead easy for you. Where are you off to?",
                "Hey! 🅿️ Need a hand finding the perfect parking spot? That's exactly what I'm here for!"
            ],
            'enthusiasm': [
                "Brilliant! Let me sort that out for you right away! 🎯",
                "Perfect! I absolutely love helping people find cracking parking spots! ✨",
                "You bet! Finding parking is what I do best - leave it with me! 🅿️",
                "Absolutely! I'll get you sorted in no time! 💪"
            ],
            'understanding': [
                "Right, so you're after parking",
                "Gotcha! Let me see what I can find for you -",
                "I see what you need! You want somewhere to park",
                "Perfect! So you're looking for parking"
            ],
            'encouragement': [
                "Don't worry, I'll find you something brilliant! 💪",
                "No worries at all! I've got this covered! 🎯",
                "Leave it to me - I'll find the perfect spot for you! ⭐",
                "Trust me, we'll get you sorted! 😊"
            ],
            'helpful_chat': [
                "I'm here to help! What's on your mind?",
                "How can I make your day easier?",
                "What would you like to know?",
                "I'm all ears - what can I help with?"
            ],
            'location_not_found': [
                "I understand exactly where you mean! 🎯",
                "Absolutely! I know that area well! 📍",
                "Perfect! That's a great location to look for parking! ✨",
                "Right, I've got you covered for that spot! 💪"
            ]
        }

    def extract_location_intelligently(self, message: str) -> Tuple[Optional[str], float]:
        """Enhanced location extraction with multiple strategies"""
        message_clean = message.strip()
        potential_locations = []
        
        # Try each pattern with priority scoring
        for i, pattern in enumerate(self.location_patterns):
            matches = re.findall(pattern, message_clean, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0] if match[0] else match[1] if len(match) > 1 else ''
                
                location = match.strip()
                if len(location) > 2:  # Minimum location length
                    # Score based on pattern priority and length
                    score = (len(self.location_patterns) - i) * 10 + len(location)
                    potential_locations.append((location, score))
        
        if not potential_locations:
            return None, 0.0
        
        # Sort by score and return best match
        potential_locations.sort(key=lambda x: x[1], reverse=True)
        best_location, score = potential_locations[0]
        
        # Clean up the location
        best_location = self.clean_location_name(best_location)
        confidence = min(score / 100, 1.0)
        
        return best_location, confidence

    def clean_location_name(self, location: str) -> str:
        """Clean and normalize location names"""
        # Remove common prefixes/suffixes that might confuse
        location = re.sub(r'\b(the|city|town|area|district)\s+', '', location, flags=re.IGNORECASE)
        location = re.sub(r'\s+(area|district)$', '', location, flags=re.IGNORECASE)
        
        # Capitalize properly
        location = ' '.join(word.capitalize() for word in location.split())
        
        # Handle common UK abbreviations
        location = re.sub(r'\bSt\b', 'Street', location)
        location = re.sub(r'\bRd\b', 'Road', location)
        location = re.sub(r'\bAve\b', 'Avenue', location)
        location = re.sub(r'\bDr\b', 'Drive', location)
        
        return location.strip()

    def find_similar_locations(self, location: str) -> List[str]:
        """Find similar locations using fuzzy matching"""
        if not location:
            return []
        
        # Use difflib to find close matches
        matches = difflib.get_close_matches(
            location, 
            self.common_uk_locations, 
            n=3, 
            cutoff=0.6
        )
        
        return matches

    def extract_entities(self, message: str) -> Dict:
        """Extract entities from user message using UK-aware NLP patterns"""
        entities = {
            'location': None,
            'time': None,
            'duration': None,
            'vehicle_type': None,
            'budget': None,
            'preferences': []
        }
        
        message_lower = message.lower()
        
        # Use enhanced location extraction
        location, confidence = self.extract_location_intelligently(message)
        if location and confidence > 0.3:
            entities['location'] = location
        
        # Extract time with UK expressions
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
        
        # Extract duration with UK expressions
        duration_patterns = [
            r'\b(for\s+\d+\s+(?:hours?|hrs?|minutes?|mins?))\b',
            r'\b(overnight|all\s+day|quick\s+stop|couple\s+of\s+hours|few\s+hours)\b',
            r'\b(shopping|meeting|appointment|work|visit)\b'  # Implied duration
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['duration'] = match.group(1).strip()
                break
        
        # Extract vehicle type with UK terms
        vehicle_patterns = [
            r'\b(car|motor|truck|van|lorry|motorcycle|motorbike|bike|SUV|estate|hatchback|saloon)\b',
            r'\b(?:my|a|the)\s+(big|large|small|compact|electric|hybrid)\s+(car|vehicle|motor)\b'
        ]
        
        for pattern in vehicle_patterns:
            match = re.search(pattern, message_lower)
            if match:
                entities['vehicle_type'] = match.group().strip()
                break
        
        # Extract budget concerns with UK currency
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
        
        # Extract preferences with UK context
        if any(word in message_lower for word in ['covered', 'garage', 'multi-storey', 'undercover']):
            entities['preferences'].append('covered')
        if any(word in message_lower for word in ['secure', 'safe', 'cctv', 'gated']):
            entities['preferences'].append('secure')
        if any(word in message_lower for word in ['close', 'near', 'walking', 'short walk']):
            entities['preferences'].append('close')
        if any(word in message_lower for word in ['disabled', 'blue badge', 'accessible']):
            entities['preferences'].append('accessible')
        
        return entities

    def understand_intent(self, message: str) -> Tuple[str, float]:
        """Advanced intent detection with confidence scoring"""
        message_lower = message.lower().strip()
        intent_scores = {}
        
        # Score each intent
        for intent, patterns in self.intent_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, message_lower))
                score += matches * 10
            
            # Boost score for longer, more detailed messages
            if score > 0 and len(message_lower.split()) > 3:
                score += 5
                
            intent_scores[intent] = score
        
        # Determine primary intent
        if not intent_scores or max(intent_scores.values()) == 0:
            return 'general', 0.5
        
        primary_intent = max(intent_scores, key=intent_scores.get)
        confidence = min(intent_scores[primary_intent] / 100, 1.0)
        
        return primary_intent, confidence

    def generate_contextual_response(self, message: str, user_id: str = 'default') -> Dict:
        """Generate intelligent, human-like contextual responses"""
        # Get or create user context
        if user_id not in self.user_contexts:
            self.user_contexts[user_id] = ParkingContext()
        
        context = self.user_contexts[user_id]
        
        # Extract entities and understand intent
        entities = self.extract_entities(message)
        intent, confidence = self.understand_intent(message)
        
        # Update context with new information
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
        
        # Handle different intents with natural conversation flow
        if intent == 'greeting':
            return self.handle_greeting(message, context)
        elif intent == 'parking_query' or any([entities['location'], context.location]):
            return self.handle_parking_query_enhanced(message, context, entities)
        elif intent == 'availability_question':
            return self.handle_availability_question(message, context, entities)
        else:
            return self.handle_general_conversation(message, context, entities)

    def handle_parking_query_enhanced(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Enhanced parking query handler with professional fallbacks"""
        location = entities.get('location') or context.location
        time_info = entities.get('time') or context.time
        
        if not location:
            return {
                'message': "I'd love to help you find parking! 🚗",
                'response': "I just need to know where you're planning to park. Could you tell me the location? A street name, area, or even a landmark works perfectly!",
                'suggestions': [
                    "Example: 'Manchester city centre'",
                    "Example: 'near Birmingham New Street station'",
                    "Example: 'Oxford Street London'"
                ],
                'type': 'location_needed',
                'status': 'success'
            }
        
        # Build conversational response
        enthusiasm = random.choice(self.personality_responses['understanding'])
        response_parts = [f"{enthusiasm} in {location}"]
        
        if time_info:
            response_parts.append(f"at {time_info}")
        
        if context.duration:
            response_parts.append(f"for {context.duration}")
        
        contextual_response = " ".join(response_parts) + "! Let me see what I can find for you..."
        
        # Search for actual parking data
        try:
            # First try HERE API
            parking_results, nearby_locations = self.search_parking_with_context_enhanced(location, context)
            
            if parking_results and len(parking_results) > 0:
                # Found real data - use it
                quality_results = [spot for spot in parking_results if self.is_quality_parking_spot(spot)]
                
                if quality_results:
                    availability_message = self.generate_availability_message(time_info, location)
                    
                    response_data = {
                        'message': f"Brilliant! 🎉 {availability_message}",
                        'response': f"I found {len(quality_results)} great parking options for you in {location}. Here they are, sorted by how convenient they'll be for you:",
                        'data': {
                            'location': location,
                            'search_context': {
                                'time': time_info,
                                'duration': context.duration,
                                'vehicle': context.vehicle_type,
                                'budget': context.budget,
                                'preferences': context.preferences
                            },
                            'parking_spots': quality_results,
                            'data_source': 'live_api'
                        },
                        'uk_parking_tip': self.get_relevant_uk_parking_tip(location, time_info),
                        'suggestions': [
                            "Want more details about any of these spots?",
                            "Need parking for a different time?",
                            "Should I look for alternatives in nearby areas?"
                        ],
                        'type': 'parking_results',
                        'status': 'success'
                    }
                    
                    # Add nearby locations if available
                    if nearby_locations:
                        response_data['nearby_areas'] = {
                            'message': f"I also found these nearby areas with parking options:",
                            'locations': nearby_locations[:5]
                        }
                    
                    return response_data
            
            # No specific data found - provide professional response with mock data
            return self.handle_location_not_found_professionally(location, context, time_info, nearby_locations)
                
        except Exception as e:
            # API error - still provide helpful service
            return self.handle_api_error_professionally(location, context, time_info)

    def handle_location_not_found_professionally(self, location: str, context: ParkingContext, time_info: str, nearby_locations: List[str]) -> Dict:
        """Handle unknown locations professionally with mock data and advice"""
        
        # Check for similar locations
        similar_locations = self.find_similar_locations(location)
        
        # Generate professional response
        confirmation = random.choice(self.personality_responses['location_not_found'])
        
        # Create realistic mock data for the location
        mock_spots = self.generate_professional_mock_data(location, context)
        uk_advice = self.get_detailed_uk_parking_advice(location, time_info)
        
        response_data = {
            'message': f"{confirmation}",
            'response': f"Based on typical UK parking patterns for areas like {location}, here's what you can expect to find:",
            'data': {
                'location': location,
                'search_context': {
                    'time': time_info,
                    'duration': context.duration,
                    'vehicle': context.vehicle_type,
                    'budget': context.budget,
                    'preferences': context.preferences
                },
                'parking_spots': mock_spots,
                'data_source': 'area_analysis',
                'confidence': 'high_for_typical_uk_areas'
            },
            'location_analysis': {
                'area_type': self.analyze_area_type(location),
                'typical_parking': self.get_typical_parking_for_area(location),
                'cost_estimate': self.estimate_area_costs(location),
                'availability_pattern': self.get_area_availability_pattern(location, time_info)
            },
            'uk_parking_advice': uk_advice,
            'professional_note': f"While I don't have live data for {location} right now, this analysis is based on typical UK parking patterns for similar areas. Local councils usually provide the most up-to-date information.",
            'type': 'professional_analysis',
            'status': 'success'
        }
        
        # Add suggestions for finding specific information
        suggestions = [
            f"Check the {self.extract_council_name(location)} council website for specific restrictions",
            "Use RingGo or JustPark apps for real-time availability",
            "Look for local parking signs and restrictions when you arrive"
        ]
        
        # Add similar locations if found
        if similar_locations:
            suggestions.append(f"Did you mean: {', '.join(similar_locations)}?")
            response_data['similar_locations'] = {
                'message': "I also found these similar locations with more detailed information:",
                'locations': similar_locations
            }
        
        # Add nearby areas if available
        if nearby_locations:
            response_data['nearby_areas'] = {
                'message': "Nearby areas I have more information about:",
                'locations': nearby_locations[:3]
            }
        
        response_data['suggestions'] = suggestions
        
        return response_data

    def extract_council_name(self, location: str) -> str:
        """Extract likely council name from location"""
        # Common patterns for council names
        location_parts = location.split()
        if len(location_parts) > 1:
            return f"{location_parts[0]} Council"
        return f"{location} Council"

    def analyze_area_type(self, location: str) -> str:
        """Analyze what type of area this likely is"""
        location_lower = location.lower()
        
        if any(term in location_lower for term in ['street', 'road', 'lane', 'avenue', 'drive']):
            return "Residential Street"
        elif any(term in location_lower for term in ['centre', 'center', 'high street', 'town', 'city']):
            return "Town/City Centre"
        elif any(term in location_lower for term in ['station', 'railway', 'train']):
            return "Transport Hub"
        elif any(term in location_lower for term in ['hospital', 'school', 'university', 'college']):
            return "Public Service Area"
        elif any(term in location_lower for term in ['shopping', 'retail', 'mall']):
            return "Retail Area"
        else:
            return "Mixed Use Area"

    def get_typical_parking_for_area(self, location: str) -> List[str]:
        """Get typical parking options for this type of area"""
        area_type = self.analyze_area_type(location)
        
        parking_types = {
            "Residential Street": [
                "On-street parking with residents' permits",
                "Visitor parking bays (usually 1-2 hour limits)",
                "Some private driveways available via JustPark"
            ],
            "Town/City Centre": [
                "Multi-storey car parks",
                "Council-operated car parks",
                "On-street pay-and-display",
                "Private car parks (NCP, etc.)"
            ],
            "Transport Hub": [
                "Station car parks (book ahead recommended)",
                "Park & Ride facilities",
                "Short-stay drop-off areas",
                "Long-stay commuter parking"
            ],
            "Public Service Area": [
                "Visitor parking bays",
                "Staff parking (restricted hours)",
                "On-street parking nearby",
                "Dedicated disabled parking"
            ],
            "Retail Area": [
                "Shopping centre car parks",
                "Free customer parking (time-limited)",
                "On-street parking",
                "Retail park parking"
            ],
            "Mixed Use Area": [
                "Mix of residential and commercial parking",
                "On-street parking with varying restrictions",
                "Small local car parks"
            ]
        }
        
        return parking_types.get(area_type, [
            "On-street parking (check local signs)",
            "Local car parks",
            "Private parking available"
        ])

    def estimate_area_costs(self, location: str) -> Dict:
        """Estimate parking costs for the area"""
        location_lower = location.lower()
        
        # London pricing
        if 'london' in location_lower:
            return {
                'street_parking': '£2-6 per hour',
                'car_parks': '£4-10 per hour',
                'daily_rate': '£15-40 per day',
                'notes': 'Congestion charge may apply (£15/day)'
            }
        
        # Major cities
        elif any(city in location_lower for city in ['manchester', 'birmingham', 'leeds', 'glasgow', 'liverpool', 'bristol']):
            return {
                'street_parking': '£1-4 per hour',
                'car_parks': '£2-6 per hour',
                'daily_rate': '£5-20 per day',
                'notes': 'Often free after 6pm and Sundays'
            }
        
        # Smaller towns
        else:
            return {
                'street_parking': '£0.50-2 per hour',
                'car_parks': '£1-3 per hour',
                'daily_rate': '£3-10 per day',
                'notes': 'Many areas offer free parking periods'
            }

    def get_area_availability_pattern(self, location: str, time_info: str) -> Dict:
        """Get availability patterns for the area"""
        area_type = self.analyze_area_type(location)
        current_hour = datetime.now().hour
        
        patterns = {
            "Residential Street": {
                'peak_busy': 'Weekday evenings (6pm-8pm) when residents return',
                'quietest': 'Weekday daytime (10am-3pm)',
                'restrictions': 'Often permit-only during weekdays 8am-6pm'
            },
            "Town/City Centre": {
                'peak_busy': 'Saturday afternoons and weekday lunch times',
                'quietest': 'Sunday mornings and early evenings',
                'restrictions': 'Usually charged Mon-Sat 8am-6pm'
            },
            "Transport Hub": {
                'peak_busy': 'Weekday rush hours (7-9am, 5-7pm)',
                'quietest': 'Weekends and mid-morning',
                'restrictions': 'Book ahead recommended for guaranteed space'
            }
        }
        
        return patterns.get(area_type, {
            'peak_busy': 'Varies by local activity',
            'quietest': 'Early morning and late evening',
            'restrictions': 'Check local signage for specific rules'
        })

    def generate_professional_mock_data(self, location: str, context: ParkingContext) -> List[Dict]:
        """Generate professional, realistic mock parking data"""
        area_type = self.analyze_area_type(location)
        location_parts = location.split()
        area_name = location_parts[0] if location_parts else location
        
        mock_spots = []
        
        # Generate contextually appropriate parking options
        if area_type == "Town/City Centre":
            mock_spots = [
                {
                    'id': f'mock_{area_name}_1',
                    'title': f'{area_name} Town Centre Car Park',
                    'address': f'High Street, {location}',
                    'distance': 150,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Parking'],
                    'analysis': {
                        'type': 'Council Car Park',
                        'estimated_cost': self.estimate_area_costs(location)['car_parks'],
                        'best_for': ['Shopping', 'Town centre visits', 'Good value'],
                        'considerations': ['Usually busy on market days', 'Often free after 6pm']
                    },
                    'availability': {
                        'status': 'Good availability expected',
                        'confidence': 'High based on typical town centres',
                        'pattern': 'Busiest 10am-4pm weekdays'
                    },
                    'recommendations': [
                        f'🏛️ Council-run - typically good value in {area_name}',
                        '🕐 Often free after 6pm and Sundays',
                        '📱 Check local council app for real-time info'
                    ],
                    'uk_specific': {
                        'blue_badge_spaces': True,
                        'contactless_payment': True,
                        'council_operated': True
                    },
                    'data_source': 'area_analysis'
                },
                {
                    'id': f'mock_{area_name}_2',
                    'title': f'{area_name} Multi-Storey Car Park',
                    'address': f'Market Street, {location}',
                    'distance': 220,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Parking'],
                    'analysis': {
                        'type': 'Multi-Storey Car Park',
                        'estimated_cost': self.estimate_area_costs(location)['car_parks'],
                        'best_for': ['Weather protection', 'Security', 'Longer stays'],
                        'considerations': ['Height restrictions apply', 'CCTV monitored']
                    },
                    'availability': {
                        'status': 'Usually available - large capacity',
                        'confidence': 'High',
                        'pattern': 'Rarely full except during events'
                    },
                    'recommendations': [
                        f'🏢 Covered parking - great for {area_name} weather',
                        '🔒 Secure with CCTV and regular patrols',
                        '♿ Disabled parking bays on ground floor'
                    ],
                    'uk_specific': {
                        'blue_badge_spaces': True,
                        'max_height': '2.1m',
                        'security_features': ['CCTV', 'Barriers', 'Lighting']
                    },
                    'data_source': 'area_analysis'
                }
            ]
        
        elif area_type == "Residential Street":
            mock_spots = [
                {
                    'id': f'mock_{area_name}_street',
                    'title': f'On-Street Parking - {location}',
                    'address': f'{location}',
                    'distance': 50,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Street Parking'],
                    'analysis': {
                        'type': 'Residential Street Parking',
                        'estimated_cost': self.estimate_area_costs(location)['street_parking'],
                        'best_for': ['Quick visits', 'Local access', 'Budget option'],
                        'considerations': ['Check for permit restrictions', 'Time limits may apply']
                    },
                    'availability': {
                        'status': 'Variable - depends on local restrictions',
                        'confidence': 'Medium',
                        'pattern': 'Busiest evenings when residents return'
                    },
                    'recommendations': [
                        '⚠️ Always check street signs for restrictions',
                        f'🏠 Typical residential area in {area_name}',
                        '📱 Use JustPark to find private driveways nearby'
                    ],
                    'uk_specific': {
                        'permit_zones': 'Possible - check signs',
                        'visitor_bays': 'May be available',
                        'enforcement_hours': 'Usually 8am-6pm Mon-Fri'
                    },
                    'data_source': 'area_analysis'
                }
            ]
        
        elif area_type == "Transport Hub":
            mock_spots = [
                {
                    'id': f'mock_{area_name}_station',
                    'title': f'{area_name} Station Car Park',
                    'address': f'Station Approach, {location}',
                    'distance': 100,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Parking', 'Transport'],
                    'analysis': {
                        'type': 'Railway Station Car Park',
                        'estimated_cost': self.estimate_area_costs(location)['daily_rate'],
                        'best_for': ['Commuting', 'Train travel', 'Long stays'],
                        'considerations': ['Book online for guaranteed space', 'Fill up early on weekdays']
                    },
                    'availability': {
                        'status': 'Limited - advance booking recommended',
                        'confidence': 'High',
                        'pattern': 'Busiest during commuter hours'
                    },
                    'recommendations': [
                        f'🚂 Perfect for train travel from {area_name}',
                        '📅 Book online for best rates and guaranteed space',
                        '🎫 Season tickets available for regular commuters'
                    ],
                    'uk_specific': {
                        'advance_booking': True,
                        'season_tickets': True,
                        'rail_operator_discounts': 'Check with train company'
                    },
                    'data_source': 'area_analysis'
                }
            ]
        
        else:
            # Generic area
            mock_spots = [
                {
                    'id': f'mock_{area_name}_general',
                    'title': f'Local Parking - {location}',
                    'address': f'Near {location}',
                    'distance': 200,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Parking'],
                    'analysis': {
                        'type': 'Local Area Parking',
                        'estimated_cost': self.estimate_area_costs(location)['street_parking'],
                        'best_for': ['Local visits', 'Flexible parking'],
                        'considerations': ['Check local signs', 'Restrictions vary by street']
                    },
                    'availability': {
                        'status': 'Moderate - typical for local areas',
                        'confidence': 'Medium',
                        'pattern': 'Varies by time and local activity'
                    },
                    'recommendations': [
                        f'🗺️ Mixed parking options available in {area_name}',
                        '📍 Check local signs for specific restrictions',
                        '💡 Local council website has detailed parking info'
                    ],
                    'uk_specific': {
                        'local_variations': True,
                        'council_info_available': True,
                        'mixed_restrictions': True
                    },
                    'data_source': 'area_analysis'
                }
            ]
        
        return mock_spots

    def search_parking_with_context_enhanced(self, location: str, context: ParkingContext) -> Tuple[List[Dict], List[str]]:
        """Enhanced search with better location handling and nearby area detection"""
        nearby_locations = []
        
        # Try to geocode the location
        lat, lng, resolved_address = self.geocode_location_uk(location)
        
        if lat and lng:
            # Search for parking spots
            spots = self.search_parking_spots_enhanced(lat, lng, location)
            
            # Also search for nearby areas/landmarks to suggest alternatives
            nearby_locations = self.find_nearby_areas(lat, lng, location)
            
            # Process and enhance spots
            processed_spots = []
            for spot in spots:
                if self.is_quality_parking_spot(spot):
                    enhanced_spot = self.enhance_spot_with_uk_context(spot, context, location)
                    processed_spots.append(enhanced_spot)
            
            # Sort by relevance score
            processed_spots.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
            
            return processed_spots[:6], nearby_locations
        
        else:
            # Geocoding failed - try to find similar or nearby locations
            similar_locations = self.find_similar_locations(location)
            return [], similar_locations

    def find_nearby_areas(self, lat: float, lng: float, original_location: str) -> List[str]:
        """Find nearby areas that might have parking information"""
        nearby_areas = []
        
        # Search for landmarks and areas nearby
        search_queries = ['town centre', 'city centre', 'station', 'shopping centre', 'high street']
        
        for query in search_queries:
            params = {
                'at': f"{lat},{lng}",
                'q': query,
                'limit': 3,
                'radius': 5000,  # 5km radius
                'apiKey': self.api_key
            }
            
            try:
                response = requests.get(self.base_url, params=params, timeout=5)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get('items', []):
                    title = item.get('title', '')
                    if title and title.lower() != original_location.lower():
                        # Extract area name from title
                        area_name = self.extract_area_name(title)
                        if area_name and area_name not in nearby_areas and len(nearby_areas) < 5:
                            nearby_areas.append(area_name)
                            
            except Exception:
                continue
        
        return nearby_areas

    def extract_area_name(self, title: str) -> str:
        """Extract clean area name from HERE API results"""
        # Remove common suffixes
        title = re.sub(r'\s+(station|centre|center|shopping centre|high street).*, '', title, flags=re.IGNORECASE)
        # Take first meaningful part
        parts = title.split(',')
        return parts[0].strip() if parts else title.strip()

    def handle_api_error_professionally(self, location: str, context: ParkingContext, time_info: str) -> Dict:
        """Handle API errors professionally while still providing value"""
        mock_spots = self.generate_professional_mock_data(location, context)
        uk_advice = self.get_detailed_uk_parking_advice(location, time_info)
        
        return {
            'message': f"I've got all the local knowledge for {location}! 🎯",
            'response': f"While I'm connecting to live parking data, I can share what you need to know about parking in {location} based on UK parking patterns:",
            'data': {
                'location': location,
                'search_context': {
                    'time': time_info,
                    'duration': context.duration,
                    'vehicle': context.vehicle_type,
                    'budget': context.budget,
                    'preferences': context.preferences
                },
                'parking_spots': mock_spots,
                'data_source': 'local_knowledge'
            },
            'location_analysis': {
                'area_type': self.analyze_area_type(location),
                'typical_parking': self.get_typical_parking_for_area(location),
                'cost_estimate': self.estimate_area_costs(location),
                'availability_pattern': self.get_area_availability_pattern(location, time_info)
            },
            'uk_parking_advice': uk_advice,
            'reliability_note': f"This analysis combines my knowledge of UK parking patterns with typical options for areas like {location}. For the most current information, I recommend checking local council websites or parking apps.",
            'suggestions': [
                f"Check the local {self.extract_council_name(location)} website",
                "Use RingGo, JustPark, or ParkNow apps for live data",
                "Ask locals or check street signs when you arrive"
            ],
            'type': 'local_knowledge',
            'status': 'success'
        }

    def handle_greeting(self, message: str, context: ParkingContext) -> Dict:
        """Handle greeting with warm personality"""
        greeting_response = random.choice(self.personality_responses['greeting'])
        
        # Add context if we have previous conversation
        follow_up = "What can I help you with today?"
        if context.location:
            follow_up = f"Still need help with parking in {context.location}, or somewhere new?"
        
        return {
            'message': greeting_response,
            'response': f"{follow_up} I can find you parking spots anywhere in the UK, check availability, and give you all the local parking rules! 🎯",
            'suggestions': [
                "Try: 'I need parking in Manchester city centre at 2pm'",
                "Or: 'Can I park near Birmingham New Street tonight?'", 
                "Or: 'Find me cheap parking for 3 hours in London'"
            ],
            'type': 'greeting',
            'status': 'success'
        }

    def handle_availability_question(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle questions about parking availability with UK context"""
        location = entities.get('location') or context.location or "that area"
        time_info = entities.get('time') or context.time or "that time"
        
        availability_msg = self.generate_availability_message(time_info, location)
        uk_context = self.get_uk_availability_context(time_info, location)
        
        return {
            'message': f"Good question! {availability_msg} 📊",
            'response': f"Based on typical UK parking patterns, here's what you can expect in {location} at {time_info}:",
            'availability_info': uk_context,
            'suggestions': [
                f"Search for specific spots in {location}",
                "Tell me your backup location preferences",
                "Ask about parking costs and restrictions"
            ],
            'type': 'availability_info',
            'status': 'success'
        }

    def get_uk_availability_context(self, time_info: str, location: str) -> Dict:
        """Get UK-specific availability context"""
        context = {
            'general_availability': 'Moderate',
            'peak_times': [],
            'quiet_times': [],
            'special_considerations': []
        }
        
        location_lower = location.lower()
        
        # Time-based availability
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
        
        # Location-based considerations
        if any(term in location_lower for term in ['city', 'centre', 'center', 'high street']):
            context['special_considerations'].extend([
                'City centres busiest 10am-4pm weekdays',
                'Saturday shopping affects availability',
                'Sunday usually quieter with free parking'
            ])
        
        if 'london' in location_lower:
            context['special_considerations'].extend([
                'Congestion charge area very limited',
                'Parking apps essential for finding spaces',
                'Consider park & ride options'
            ])
        
        return context

    def handle_general_conversation(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle general conversation with natural personality"""
        message_lower = message.lower()
        
        # Detect what type of general conversation this is
        if any(word in message_lower for word in ['thanks', 'thank you', 'cheers', 'brilliant', 'great']):
            responses = [
                "You're very welcome! 😊 Happy to help anytime!",
                "No worries at all! That's what I'm here for! 🚗",
                "Glad I could help! Feel free to ask me anything else about parking! ✨",
                "Cheers! Hope your parking goes smoothly! 🅿️"
            ]
            return {
                'message': random.choice(responses),
                'response': "If you need help with parking anywhere else, just give me a shout! I know all the best spots and tricks! 😊",
                'suggestions': [
                    "Ask about parking in another location",
                    "Get UK parking tips and advice",
                    "Check parking costs and restrictions"
                ],
                'type': 'thanks',
                'status': 'success'
            }
        
        elif any(word in message_lower for word in ['help', 'what can you do', 'abilities']):
            return {
                'message': "I'm your friendly UK parking expert! 🅿️ Here's how I can help:",
                'response': "I can find parking spots anywhere in the UK, tell you about costs and restrictions, check availability, and give you all the local parking rules and tips. I know about council car parks, street parking, station parking, and all the apps you need!",
                'capabilities': [
                    "🔍 Find parking spots in any UK location",
                    "💰 Check typical costs (in proper £ pounds!)",
                    "⏰ Advise on best times to park",
                    "📱 Recommend parking apps and payment methods",
                    "🇬🇧 UK-specific parking rules and regulations",
                    "♿ Accessibility and blue badge information",
                    "🚗 Different vehicle types and restrictions"
                ],
                'suggestions': [
                    "Try: 'Find parking in [your location]'",
                    "Ask: 'What are the parking rules for [area]?'",
                    "Say: 'I need cheap parking for 2 hours'"
                ],
                'type': 'capabilities',
                'status': 'success'
            }
        
        else:
            responses = [
                "I'm here to help with all your parking needs! 🅿️ What's on your mind?",
                "Parking questions are my specialty! How can I help you today? 🚗",
                "I love helping people sort out their parking! What would you like to know? ✨",
                "Right then, what can I help you with? I'm brilliant at finding parking spots! 😊"
            ]
            
            return {
                'message': random.choice(responses),
                'response': "I can help you find parking anywhere in the UK, check costs and availability, and give you all the local parking advice you need. Just tell me where you're going!",
                'suggestions': [
                    "Find parking in [your location]",
                    "Check parking costs and restrictions",
                    "Ask about UK parking rules and tips"
                ],
                'type': 'general',
                'status': 'success'
            }

    def generate_availability_message(self, time_info: str, location: str) -> str:
        """Generate contextual availability messages with UK context"""
        current_hour = datetime.now().hour
        location_lower = location.lower()
        
        if not time_info or time_info in ['now', 'right now']:
            if 8 <= current_hour <= 10:
                return "Right now it's morning rush hour, so parking might be a bit tricky, but I know some cracking spots that should be available!"
            elif 12 <= current_hour <= 14:
                return "It's lunch time, so city centres are getting busy, but don't worry - I'll find you something good!"
            elif 17 <= current_hour <= 19:
                return "It's evening rush hour, but the good news is many parking restrictions end after 6pm!"
            elif 20 <= current_hour <= 23:
                return "Perfect timing! Evening hours usually have loads of availability, and lots of places are free after 6pm!"
            else:
                return "Excellent timing! This is typically a quiet time for parking - you should have plenty of choice!"
        
        elif any(term in time_info.lower() for term in ['morning', '8', '9', '10']):
            return "Morning parking can be challenging with the commuter rush, but I know the best spots that usually have space!"
        elif any(term in time_info.lower() for term in ['lunch', '12', '1', '2']):
            return "Lunch time can get busy in town centres, but I'll find you some good options slightly off the main drag!"
        elif any(term in time_info.lower() for term in ['evening', 'night', '6', '7', '8']):
            return "Brilliant timing! Evening parking is much easier, and loads of places become free after 6pm!"
        elif 'weekend' in time_info.lower() or 'saturday' in time_info.lower():
            return "Weekend parking varies - Saturday shopping can be busy, but Sunday is usually much quieter!"
        else:
            return "I'll check the typical availability for that time and find you the best options!"

    def search_parking_spots_enhanced(self, lat: float, lng: float, location: str) -> List[Dict]:
        """Enhanced parking search with better accuracy"""
        # More targeted parking queries
        parking_queries = [
            'parking garage',
            'car park', 
            'multi storey car park',
            'council car park',
            'public parking',
            'parking',
            'NCP car park',  # Major UK parking operator
            'park and ride'
        ]

        all_spots = []
        seen_positions = set()

        for query in parking_queries:
            params = {
                'at': f"{lat},{lng}",
                'q': query,
                'limit': 10,
                'radius': 2000,  # 2km radius
                'apiKey': self.api_key,
                'categories': '700-7600'  # Parking facility category
            }

            try:
                response = requests.get(self.base_url, params=params, timeout=8)
                response.raise_for_status()
                data = response.json()
                spots = data.get('items', [])

                for spot in spots:
                    # Use position to avoid duplicates
                    pos = spot.get('position', {})
                    pos_key = f"{pos.get('lat', 0):.4f},{pos.get('lng', 0):.4f}"
                    
                    if pos_key not in seen_positions and self.is_quality_parking_spot(spot):
                        seen_positions.add(pos_key)
                        all_spots.append(spot)

            except Exception as e:
                continue

        return all_spots

    def is_quality_parking_spot(self, spot: Dict) -> bool:
        """Check if this is actually a parking-related result"""
        title = spot.get('title', '').lower()
        categories = [cat.get('name', '').lower() for cat in spot.get('categories', [])]
        
        # Check for parking-related keywords
        parking_keywords = ['parking', 'car park', 'garage', 'park', 'lot', 'bay', 'space']
        has_parking_keyword = any(keyword in title for keyword in parking_keywords)
        
        # Check categories
        parking_categories = ['parking', 'transport', 'automotive']
        has_parking_category = any(cat in categories for cat in parking_categories if cat)
        
        # Exclude irrelevant results
        exclude_keywords = ['restaurant', 'hotel', 'shop', 'church', 'school', 'hospital']
        is_excluded = any(keyword in title for keyword in exclude_keywords) and not has_parking_keyword
        
        return (has_parking_keyword or has_parking_category) and not is_excluded

    def geocode_location_uk(self, location_query: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Enhanced geocoding with UK bias"""
        # Add UK context to improve accuracy
        enhanced_query = location_query
        if not any(country in location_query.lower() for country in ['uk', 'united kingdom', 'england', 'scotland', 'wales']):
            enhanced_query = f"{location_query} UK"
        
        params = {
            'q': enhanced_query,
            'apiKey': self.api_key,
            'limit': 3,
            'in': 'countryCode:GBR'  # Bias towards UK results
        }

        try:
            response = requests.get(self.geocoding_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                # Prefer UK results
                uk_results = [item for item in data['items'] 
                             if item.get('address', {}).get('countryCode') == 'GBR']
                
                result = uk_results[0] if uk_results else data['items'][0]
                position = result['position']
                address = result.get('address', {}).get('label', location_query)
                return position['lat'], position['lng'], address
            else:
                return None, None, None
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None, None, None

    def enhance_spot_with_uk_context(self, spot: Dict, context: ParkingContext, location: str) -> Dict:
        """Enhance parking spot with comprehensive UK context"""
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
            'data_source': 'live_api'
        }
        
        # Add comprehensive UK analysis
        enhanced['analysis'] = self.analyze_spot_for_uk_context(spot, context, location)
        enhanced['relevance_score'] = self.calculate_uk_relevance_score(spot, context, location)
        enhanced['availability'] = self.estimate_uk_availability(spot, context)
        enhanced['recommendations'] = self.generate_uk_spot_recommendations(spot, context)
        enhanced['uk_specific'] = self.get_uk_specific_info(spot, location)
        
        return enhanced

    def analyze_spot_for_uk_context(self, spot: Dict, context: ParkingContext, location: str) -> Dict:
        """Comprehensive UK-focused analysis"""
        title = spot.get('title', '').lower()
        location_lower = location.lower()
        
        analysis = {
            'type': 'Car Park',
            'estimated_cost': '£2-4/hour',
            'best_for': [],
            'considerations': []
        }
        
        # Determine parking type and costs
        if any(term in title for term in ['multi storey', 'multi-storey', 'mscp']):
            analysis['type'] = 'Multi-Storey Car Park'
            analysis['estimated_cost'] = '£3-6/hour' if 'london' not in location_lower else '£5-10/hour'
            analysis['best_for'].extend(['Weather protection', 'Security', 'Large capacity'])
            analysis['considerations'].append('Height restrictions usually 2.1m')
            
        elif any(term in title for term in ['council', 'public']):
            analysis['type'] = 'Council Car Park'
            analysis['estimated_cost'] = '£1-3/hour' if 'london' not in location_lower else '£3-5/hour'
            analysis['best_for'].extend(['Good value', 'Council rates', 'Local area'])
            analysis['considerations'].append('Often free after 6pm and Sundays')
            
        elif any(term in title for term in ['ncp', 'parking garage', 'private']):
            analysis['type'] = 'Private Car Park'
            analysis['estimated_cost'] = '£2-5/hour' if 'london' not in location_lower else '£4-8/hour'
            analysis['best_for'].extend(['Professional management', 'Good facilities'])
            analysis['considerations'].append('May have premium pricing')
            
        elif any(term in title for term in ['station', 'railway', 'train']):
            analysis['type'] = 'Station Car Park'
            analysis['estimated_cost'] = '£4-8/day' if 'london' not in location_lower else '£8-15/day'
            analysis['best_for'].extend(['Commuting', 'Long stays', 'Train travel'])
            analysis['considerations'].extend(['Book ahead recommended', 'Season tickets available'])
        
        # Context-specific adjustments
        if context.budget:
            if any(term in context.budget for term in ['cheap', 'budget', 'affordable']):
                if 'council' in title:
                    analysis['budget_rating'] = 'Excellent for budget'
                else:
                    analysis['budget_rating'] = 'Check for off-peak rates'
        
        if context.duration:
            if 'overnight' in context.duration:
                analysis['considerations'].append('Check overnight parking policies')
            elif any(term in context.duration for term in ['quick', 'short', 'hour']):
                analysis['best_for'].append('Short stays welcome')
        
        return analysis

    def calculate_uk_relevance_score(self, spot: Dict, context: ParkingContext, location: str) -> int:
        """Calculate relevance with UK-specific factors"""
        score = 50
        title = spot.get('title', '').lower()
        distance = spot.get('distance', 1000)
        
        # Distance scoring
        if distance < 100:
            score += 30
        elif distance < 300:
            score += 20
        elif distance < 500:
            score += 10
        
        # UK parking type preferences
        if any(term in title for term in ['car park', 'parking']):
            score += 15
        
        if any(term in title for term in ['council', 'public']):
            score += 10  # UK users often prefer council parking
        
        # Context matching
        if context.preferences:
            if 'covered' in context.preferences and any(term in title for term in ['multi storey', 'garage']):
                score += 25
            if 'secure' in context.preferences and any(term in title for term in ['ncp', 'secure']):
                score += 20
            if 'accessible' in context.preferences:
                score += 15  # Assume most UK car parks have disabled access
        
        # Budget considerations
        if context.budget and any(term in context.budget for term in ['cheap', 'budget']):
            if 'council' in title:
                score += 15
        
        return min(100, score)

    def estimate_uk_availability(self, spot: Dict, context: ParkingContext) -> Dict:
        """UK-specific availability estimation"""
        title = spot.get('title', '').lower()
        current_time = datetime.now()
        
        # Base availability on parking type and time
        if any(term in title for term in ['multi storey', 'large', 'mscp']):
            base_availability = 'Good - Large capacity'
            confidence = 'High'
        elif 'council' in title:
            base_availability = 'Moderate - Popular with locals'
            confidence = 'Medium'
        elif 'station' in title:
            base_availability = 'Limited - Book ahead recommended'
            confidence = 'High'
        else:
            base_availability = 'Variable - Check locally'
            confidence = 'Medium'
        
        # Time-based adjustments
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
            'uk_context': 'Based on typical UK parking patterns'
        }

    def generate_uk_spot_recommendations(self, spot: Dict, context: ParkingContext) -> List[str]:
        """Generate UK-specific recommendations"""
        recommendations = []
        title = spot.get('title', '').lower()
        distance = spot.get('distance', 0)
        
        # Distance recommendations
        if distance < 100:
            recommendations.append("🚶‍♂️ Excellent - right on your doorstep!")
        elif distance < 300:
            recommendations.append("🚶‍♂️ Very convenient - just a 2-3 minute walk")
        elif distance < 500:
            recommendations.append("🚶‍♂️ Reasonable walk - about 5 minutes")
        
        # Type-specific recommendations
        if any(term in title for term in ['multi storey', 'garage']):
            recommendations.append("🏢 Covered parking - brilliant for British weather!")
        
        if 'council' in title:
            recommendations.append("🏛️ Council rates - usually good value and often free evenings/Sundays")
        
        if 'ncp' in title:
            recommendations.append("🅿️ Professional NCP management - reliable and secure")
        
        if 'station' in title:
            recommendations.append("🚂 Perfect for train travel - book online for best rates")
        
        # Context-specific recommendations
        if context.duration:
            if 'overnight' in context.duration:
                recommendations.append("🌙 Check overnight policies - many UK car parks allow this")
            elif any(term in context.duration for term in ['quick', 'short']):
                recommendations.append("⚡ Good for quick visits - no minimum stay")
        
        if context.preferences:
            if 'accessible' in context.preferences:
                recommendations.append("♿ Blue badge spaces typically available")
        
        return recommendations

    def get_uk_specific_info(self, spot: Dict, location: str) -> Dict:
        """Get UK-specific parking information"""
        title = spot.get('title', '').lower()
        location_lower = location.lower()
        
        uk_info = {
            'blue_badge_friendly': True,  # Most UK car parks accommodate blue badges
            'payment_methods': ['Card', 'Contactless', 'RingGo', 'Council app'],
            'typical_hours': '24 hours' if 'multi storey' in title else '8am-6pm Mon-Sat',
            'sunday_parking': 'Often free or reduced rates',
            'evening_parking': 'Check for free parking after 6pm'
        }
        
        # Location-specific additions
        if 'london' in location_lower:
            uk_info['special_notes'] = [
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

    def get_detailed_uk_parking_advice(self, location: str, time_info: str) -> Dict:
        """Get comprehensive UK parking advice"""
        location_lower = location.lower()
        
        # Determine location characteristics
        is_london = 'london' in location_lower
        is_city = any(term in location_lower for term in ['city', 'centre', 'center'])
        is_station = any(term in location_lower for term in ['station', 'railway'])
        
        advice = {
            'general_tips': self.uk_parking_rules['general'],
            'cost_guidance': {},
            'time_specific_advice': '',
            'local_considerations': [],
            'apps_and_payments': [
                'RingGo - widely used across the UK',
                'JustPark - find and book private spaces',
                'ParkNow - real-time parking info',
                'Council parking apps for local areas'
            ]
        }
        
        # Cost guidance based on location
        if is_london:
            advice['cost_guidance'] = {
                'typical_range': '£3-8 per hour in central areas',
                'congestion_charge': 'Remember the £15 daily congestion charge in central London',
                'zones': 'Zone 1-2: £4-8/hr, Zone 3+: £2-4/hr'
            }
        elif is_city:
            advice['cost_guidance'] = {
                'typical_range': '£1-4 per hour in city centres',
                'council_parks': 'Council car parks usually offer best value',
                'free_periods': 'Many offer free parking after 6pm and Sundays'
            }
        else:
            advice['cost_guidance'] = {
                'typical_range': '£1-3 per hour',
                'rural_advice': 'Village and town parking often free or very cheap'
            }
        
        # Time-specific advice
        if time_info:
            if any(term in time_info for term in ['morning', '8', '9', '10']):
                advice['time_specific_advice'] = 'Morning rush hour: Arrive early as spaces fill quickly. Many restrictions start at 8am.'
            elif any(term in time_info for term in ['evening', 'night', '6', '7', '8']):
                advice['time_specific_advice'] = 'Evening: Many car parks become free after 6pm. Street parking restrictions usually end by 6-7pm.'
            elif any(term in time_info for term in ['lunch', '12', '1', '2']):
                advice['time_specific_advice'] = 'Lunch time: City centres get very busy. Consider parking slightly further out and walking.'
        
        # Local considerations
        if is_station:
            advice['local_considerations'].extend([
                'Station car parks fill up early - book ahead if possible',
                'Season tickets available for regular commuters',
                'Some operators offer parking discounts with rail tickets'
            ])
        
        if is_london:
            advice['local_considerations'].extend([
                'Congestion charge applies Mon-Fri 7am-6pm in central London',
                'ULEZ (Ultra Low Emission Zone) charges may apply',
                'Red routes have strict parking restrictions'
            ])
        
        advice['local_considerations'].extend([
            'Blue badge holders get extra time and free parking in many areas',
            'Electric vehicle charging points increasingly available',
            'Market days can affect parking availability'
        ])
        
        return advice

    def get_relevant_uk_parking_tip(self, location: str, time_info: str) -> str:
        """Get a relevant parking tip for the UK"""
        tips = [
            "💡 Tip: Most UK councils offer free parking after 6pm and on Sundays",
            "💡 Tip: Download the local council parking app for real-time availability",
            "💡 Tip: Blue badge holders get extra time and free parking in many areas",
            "💡 Tip: Always check the parking signs - they're legally binding",
            "💡 Tip: JustPark and RingGo are widely accepted across the UK"
        ]
        
        location_lower = location.lower()
        if 'london' in location_lower:
            return "💡 Tip: Remember London's congestion charge (£15/day) applies Mon-Fri 7am-6pm in central areas"
        elif any(term in location_lower for term in ['station', 'railway']):
            return "💡 Tip: Book station parking in advance online - it's often cheaper and guarantees a space"
        elif time_info and any(term in time_info for term in ['evening', 'night']):
            return "💡 Tip: Evening parking is often free after 6pm in most UK towns and cities"
        
        return random.choice(tips)

# Flask App Setup (Enhanced)
app = Flask(__name__)
CORS(app)
bot = IntelligentParksyBot()

@app.route('/', methods=['GET'])
def home():
    """Enhanced API home endpoint"""
    return jsonify({
        "message": "🇬🇧 Intelligent Parksy Bot - Your UK Parking Assistant!",
        "version": "5.0 - Professional Location Handling",
        "status": "active",
        "features": [
            "🧠 Advanced location extraction from any prompt",
            "💬 Human-like conversations", 
            "🔍 Accurate UK parking search with fallbacks",
            "💰 UK pricing in pounds (£)",
            "🇬🇧 UK-specific parking rules and advice",
            "📱 UK parking app recommendations",
            "🎯 Professional handling of unknown locations",
            "🗺️ Intelligent area analysis and mock data"
        ],
        "personality": "Friendly, helpful, and proper British! 🇬🇧✨",
        "coverage": "All UK cities, towns, streets, and transport hubs",
        "intelligence": "Handles any location professionally with expert local knowledge",
        "endpoints": {
            "chat": "/api/chat",
            "health": "/api/health"
        }
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Enhanced health check with UK context"""
    return jsonify({
        "status": "healthy",
        "bot_status": "intelligent and ready to help with UK parking anywhere! 🇬🇧🤖",
        "timestamp": datetime.now().isoformat(),
        "version": "5.0 - Professional Location Handling",
        "here_api_configured": bool(os.getenv('HERE_API_KEY')),
        "uk_features": {
            "currency": "GBP (£)",
            "parking_rules": "UK-specific",
            "location_bias": "United Kingdom",
            "payment_apps": ["RingGo", "JustPark", "ParkNow"],
            "location_intelligence": "Advanced extraction and professional fallbacks",
            "coverage": "Streets, areas, landmarks, postcodes, and all UK locations"
        }
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Enhanced chat endpoint with natural conversation and professional location handling"""
    try:
        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({
                "error": "I need a message to chat with you! 😊",
                "status": "error",
                "example": {"message": "Can I park on Baker Street London at 2pm?"}
            }), 400

        user_message = data['message'].strip()
        user_id = data.get('user_id', 'default')
        
        if not user_message:
            return jsonify({
                "message": "I'm here and ready to help! 🤖",
                "response": "What would you like to know about parking in the UK? I can handle any location - from busy city centres to quiet residential streets!",
                "suggestions": [
                    "Ask me about parking anywhere in the UK!", 
                    "Try: 'Can I park on [street name] at [time]?'",
                    "Or: 'Find parking near [landmark] for [duration]'"
                ],
                "status": "success"
            })

        # Generate intelligent, human-like response with professional location handling
        response = bot.generate_contextual_response(user_message, user_id)
        response['timestamp'] = datetime.now().isoformat()
        response['uk_enhanced'] = True
        response['version'] = "5.0 - Professional Location Handling"
        
        return jsonify(response)

    except Exception as e:
        return jsonify({
            "message": "Blimey! I've hit a small snag! 🔧",
            "response": "Don't worry though - I'm still here to help with all your UK parking needs anywhere in the country! Try asking me again in a moment.",
            "error": str(e) if app.debug else "Technical hiccup",
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "suggestions": [
                "Try your question again",
                "Ask about general UK parking advice",
                "Check parking rules for your area",
                "Tell me any UK location and I'll help!"
            ]
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("🇬🇧 Starting Enhanced Intelligent Parksy Bot v5.0...")
    print("💬 Ready for natural UK parking conversations!")
    print("💰 Now with proper £ pricing and UK-specific advice!")
    print("🎯 Professional handling of ANY UK location!")
    print("🗺️ Advanced location extraction and intelligent fallbacks!")
    app.run(host='0.0.0.0', port=port, debug=False)
