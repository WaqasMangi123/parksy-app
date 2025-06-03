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
            ]
        }

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
        
        # Extract location with UK-specific patterns
        location_patterns = [
            r'\b(?:in|at|near|around|by)\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:at|for|around|by|\d)|\s*[,.]|$)',
            r'\b([A-Z][a-zA-Z\s]+(?:street|st|road|rd|lane|avenue|ave|city|town|centre|high\s+street|market|station|hospital|university|college))\b',
            r'\b([A-Z][a-zA-Z\s]{2,})\b(?=\s+(?:at|for|around|by|\d|$))'
        ]
        
        for pattern in location_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Clean up common UK location variations
                location = re.sub(r'\b(the|city|town)\s+', '', location, flags=re.IGNORECASE)
                entities['location'] = location
                break
        
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
            return self.handle_parking_query(message, context, entities)
        elif intent == 'availability_question':
            return self.handle_availability_question(message, context, entities)
        else:
            return self.handle_general_conversation(message, context, entities)

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

    def handle_parking_query(self, message: str, context: ParkingContext, entities: Dict) -> Dict:
        """Handle parking queries with context awareness and real data"""
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
            parking_results = self.search_parking_with_context(location, context)
            
            if parking_results and len(parking_results) > 0:
                # Filter results to ensure quality
                quality_results = [spot for spot in parking_results if self.is_quality_parking_spot(spot)]
                
                if quality_results:
                    availability_message = self.generate_availability_message(time_info, location)
                    
                    return {
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
                            'parking_spots': quality_results
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
            
            # Fallback to helpful advice with mock data when real data isn't available
            mock_spots = self.generate_helpful_mock_data(location, context)
            uk_advice = self.get_detailed_uk_parking_advice(location, time_info)
            
            return {
                'message': f"Right, I've had a look around {location} for you! 🔍",
                'response': f"While I'm getting the latest parking data, here are some typical options you'll find in {location}, plus some local parking advice:",
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
                    'is_mock_data': True
                },
                'uk_parking_advice': uk_advice,
                'suggestions': [
                    f"Check local council website for {location} parking",
                    "Look for parking apps like JustPark or ParkNow",
                    "Ask about specific streets or landmarks nearby"
                ],
                'type': 'parking_advice',
                'status': 'partial'
            }
                
        except Exception as e:
            # Provide helpful advice even when there's an error
            uk_advice = self.get_detailed_uk_parking_advice(location, time_info)
            
            return {
                'message': "I'm having a bit of trouble with the live data right now, but don't worry! 🔧",
                'response': f"I can still give you loads of helpful advice about parking in {location}. Here's what you need to know:",
                'uk_parking_advice': uk_advice,
                'suggestions': [
                    f"Try the {location} council website for parking info",
                    "Use apps like JustPark, ParkNow, or RingGo",
                    "Look for local parking signs and restrictions"
                ],
                'type': 'advice',
                'status': 'advice'
            }

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

    def generate_helpful_mock_data(self, location: str, context: ParkingContext) -> List[Dict]:
        """Generate realistic mock parking data with UK context"""
        location_lower = location.lower()
        
        # Determine location type for realistic options
        is_city_centre = any(term in location_lower for term in ['centre', 'center', 'city', 'town centre', 'high street'])
        is_london = 'london' in location_lower
        is_station = any(term in location_lower for term in ['station', 'railway', 'train'])
        
        mock_spots = []
        
        if is_city_centre:
            mock_spots = [
                {
                    'id': 1,
                    'title': f'{location} Multi-Storey Car Park',
                    'address': f'City Centre, {location}',
                    'distance': 150,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Parking'],
                    'analysis': {
                        'type': 'Multi-Storey Car Park',
                        'estimated_cost': '£3-5/hour' if not is_london else '£4-8/hour',
                        'best_for': ['Weather protection', 'Security', 'CCTV'],
                        'considerations': ['Height restrictions may apply', 'Can get busy during peak times']
                    },
                    'availability': {
                        'status': 'Usually available with 200+ spaces',
                        'confidence': 'High',
                        'peak_times': '12pm-2pm and 5pm-7pm'
                    },
                    'recommendations': [
                        '🏢 Covered parking - perfect for any weather',
                        '🔒 Secure with CCTV and regular patrols',
                        '♿ Disabled parking bays available'
                    ],
                    'uk_specific': {
                        'blue_badge_spaces': True,
                        'contactless_payment': True,
                        'max_height': '2.1m'
                    }
                },
                {
                    'id': 2,
                    'title': f'{location} Council Car Park',
                    'address': f'High Street, {location}',
                    'distance': 200,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Parking'],
                    'analysis': {
                        'type': 'Council Car Park',
                        'estimated_cost': '£2-4/hour' if not is_london else '£3-6/hour',
                        'best_for': ['Good value', 'Central location', 'Short stays'],
                        'considerations': ['Limited long-stay options', 'Gets busy on market days']
                    },
                    'availability': {
                        'status': 'Moderate availability - 100 spaces',
                        'confidence': 'Medium',
                        'free_times': 'After 6pm and Sundays'
                    },
                    'recommendations': [
                        '💰 Council rates - usually good value',
                        '🕐 Often free after 6pm and Sundays',
                        '📱 RingGo payment accepted'
                    ],
                    'uk_specific': {
                        'blue_badge_spaces': True,
                        'sunday_free': True,
                        'evening_free': '6pm-8am'
                    }
                }
            ]
        
        if is_station:
            mock_spots.extend([
                {
                    'id': 3,
                    'title': f'{location} Station Car Park',
                    'address': f'Station Approach, {location}',
                    'distance': 50,
                    'coordinates': {'lat': 51.5074, 'lng': -0.1278},
                    'categories': ['Parking', 'Transport'],
                    'analysis': {
                        'type': 'Railway Station Car Park',
                        'estimated_cost': '£4-8/day' if not is_london else '£8-15/day',
                        'best_for': ['Commuting', 'Long stays', 'Train travel'],
                        'considerations': ['Book ahead for guaranteed space', 'Busy during rush hours']
                    },
                    'availability': {
                        'status': 'Limited - book ahead recommended',
                        'confidence': 'Medium',
                        'booking_required': True
                    },
                    'recommendations': [
                        '🚂 Perfect for train travel',
                        '📅 Book online for guaranteed space',
                        '🔒 Secure with barriers and CCTV'
                    ],
                    'uk_specific': {
                        'season_tickets': True,
                        'advance_booking': True,
                        'rail_discount': 'Available with some operators'
                    }
                }
            ])
        
        # Add street parking option
        mock_spots.append({
            'id': 4,
            'title': f'Street Parking near {location}',
            'address': f'Various streets near {location}',
            'distance': 300,
            'coordinates': {'lat': 51.5074, 'lng': -0.1278},
            'categories': ['Parking'],
            'analysis': {
                'type': 'On-Street Parking',
                'estimated_cost': '£1-3/hour' if not is_london else '£2-5/hour',
                'best_for': ['Quick visits', 'Budget parking', 'Flexibility'],
                'considerations': ['Check signs carefully', 'Time limits apply', 'Enforcement active']
            },
            'availability': {
                'status': 'Variable - check locally',
                'confidence': 'Low',
                'restrictions': 'Various time limits and restrictions'
            },
            'recommendations': [
                '⚠️ Always check parking signs carefully',
                '⏰ Usually 1-2 hour limits in busy areas',
                '📱 Use JustPark app to check restrictions'
            ],
            'uk_specific': {
                'residents_only': 'Some areas',
                'permit_required': 'Check signs',
                'enforcement_hours': 'Usually 8am-6pm Mon-Sat'
            }
        })
        
        return mock_spots[:3]  # Return top 3 relevant options

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

    def search_parking_with_context(self, location: str, context: ParkingContext) -> List[Dict]:
        """Search for parking with enhanced accuracy and UK context"""
        # Geocode location with UK bias
        lat, lng, address = self.geocode_location_uk(location)
        if not lat:
            return []
        
        # Search for parking spots with multiple strategies
        spots = self.search_parking_spots_enhanced(lat, lng, location)
        
        # Process and enhance with UK context
        processed_spots = []
        for spot in spots:
            if self.is_quality_parking_spot(spot):
                enhanced_spot = self.enhance_spot_with_uk_context(spot, context, location)
                processed_spots.append(enhanced_spot)
        
        # Sort by relevance score
        processed_spots.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return processed_spots[:6]  # Return top 6 quality results

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
            'categories': [cat.get('name', '') for cat in spot.get('categories', [])]
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

# Flask App Setup (Enhanced)
app = Flask(__name__)
CORS(app)
bot = IntelligentParksyBot()

@app.route('/', methods=['GET'])
def home():
    """Enhanced API home endpoint"""
    return jsonify({
        "message": "🇬🇧 Intelligent Parksy Bot - Your UK Parking Assistant!",
        "version": "4.0 - UK Enhanced with Real Data",
        "status": "active",
        "features": [
            "🧠 Natural language understanding",
            "💬 Human-like conversations", 
            "🔍 Accurate UK parking search",
            "💰 UK pricing in pounds (£)",
            "🇬🇧 UK-specific parking rules and advice",
            "📱 UK parking app recommendations"
        ],
        "personality": "Friendly, helpful, and proper British! 🇬🇧✨",
        "coverage": "All UK cities, towns, and transport hubs",
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
        "bot_status": "intelligent and ready to help with UK parking! 🇬🇧🤖",
        "timestamp": datetime.now().isoformat(),
        "version": "4.0 - UK Enhanced",
        "here_api_configured": bool(os.getenv('HERE_API_KEY')),
        "uk_features": {
            "currency": "GBP (£)",
            "parking_rules": "UK-specific",
            "location_bias": "United Kingdom",
            "payment_apps": ["RingGo", "JustPark", "ParkNow"]
        }
    })

@app.route('/api/chat', methods=['POST'])
def chat():
    """Enhanced chat endpoint with natural conversation"""
    try:
        data = request.get_json()

        if not data or 'message' not in data:
            return jsonify({
                "error": "I need a message to chat with you! 😊",
                "status": "error",
                "example": {"message": "Can I park in Manchester city centre at 2pm?"}
            }), 400

        user_message = data['message'].strip()
        user_id = data.get('user_id', 'default')
        
        if not user_message:
            return jsonify({
                "message": "I'm here and ready to help! 🤖",
                "response": "What would you like to know about parking in the UK?",
                "suggestions": ["Ask me about parking anywhere in the UK!"],
                "status": "success"
            })

        # Generate intelligent, human-like response
        response = bot.generate_contextual_response(user_message, user_id)
        response['timestamp'] = datetime.now().isoformat()
        response['uk_enhanced'] = True
        
        return jsonify(response)

    except Exception as e:
        return jsonify({
            "message": "Blimey! I've hit a small snag! 🔧",
            "response": "Don't worry though - I'm still here to help with all your UK parking needs! Try asking me again in a moment.",
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
    print("💰 Now with proper £ pricing and UK-specific advice!")
    app.run(host='0.0.0.0', port=port, debug=False)
