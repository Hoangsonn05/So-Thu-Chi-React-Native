/**
 * Firebase configuration for React Native Firebase.
 * 
 * @react-native-firebase/app reads configuration from google-services.json (Android)
 * and GoogleService-Info.plist (iOS) automatically.
 * 
 * This file re‑exports the auth & firestore instances for convenience.
 */

import auth from '@react-native-firebase/auth';
import firestore from '@react-native-firebase/firestore';
import storage from '@react-native-firebase/storage';

// Export instances/functions
export const firebaseAuth = auth;
export const firestoreDb = firestore;
export const firebaseStorage = storage;

export default { firebaseAuth, firestoreDb, firebaseStorage };
