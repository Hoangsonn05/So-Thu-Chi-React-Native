/**
 * Firebase configuration for React Native Firebase.
 * 
 * @react-native-firebase/app reads configuration from google-services.json (Android)
 * and GoogleService-Info.plist (iOS) automatically.
 * 
 * This file re‑exports the auth & firestore instances for convenience.
 */

import auth, { FirebaseAuthTypes } from '@react-native-firebase/auth';
import firestore, { FirebaseFirestoreTypes } from '@react-native-firebase/firestore';

// Firebase Auth instance
export const firebaseAuth = auth;

// Firestore instance
export const firestoreDb = firestore;

// Type re-exports for convenience
export type FirebaseUser = FirebaseAuthTypes.User;
export type FirestoreDocument = FirebaseFirestoreTypes.DocumentSnapshot;

export default { firebaseAuth, firestoreDb };
