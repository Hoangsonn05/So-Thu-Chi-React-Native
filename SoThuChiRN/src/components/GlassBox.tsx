import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { BlurView } from 'expo-blur';
import { Colors, BorderRadius, Spacing } from '../theme/colors';

interface GlassBoxProps {
  children: React.ReactNode;
  style?: ViewStyle;
  intensity?: number;
  borderRadius?: number;
  padding?: number;
  overflow?: 'visible' | 'hidden';
}

/**
 * GlassBox - Compact Scaling Edition
 */
export const GlassBox: React.FC<GlassBoxProps> = ({
  children,
  style,
  intensity = 35, // Reduced for lighter feel
  borderRadius = BorderRadius.lg,
  padding = Spacing.lg, // 12px
  overflow = 'hidden',
}) => {
  return (
    <View style={[styles.container, { borderRadius, overflow }, style]}>
      <BlurView 
        intensity={intensity} 
        tint="dark"
        style={StyleSheet.absoluteFill} 
      />
      <View style={[styles.content, { padding }]}>
        {children}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    backgroundColor: Colors.glassBg,
    borderWidth: 0.4, // Ultra-thin border
    borderColor: Colors.glassBorderStrong,
    // Refined depth
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 4,
  },
  content: {
    // Removed flex: 1 to allow wrapping children naturally
  },
});

export default GlassBox;
