import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  StyleSheet,
  Dimensions,
  PanResponder,
} from 'react-native';
import { MaterialIcons } from '@expo/vector-icons';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  Easing,
  FadeIn,
  cancelAnimation,
} from 'react-native-reanimated';
import { BlurView } from 'expo-blur';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const COLLAPSED_SIZE = 56;
const ISLAND_WIDTH = 180;
const PULSE_INTERVAL = 15000; // 15 seconds

interface AIFloatingIslandProps {
  onPress?: () => void;
  onExpandStart?: () => void;
  isExpanded?: boolean;
}

const AIFloatingIsland = React.forwardRef<View, AIFloatingIslandProps>(
  ({ onPress, onExpandStart, isExpanded = false }, ref) => {
    const [islandState, setIslandState] = useState<'collapsed' | 'island'>('collapsed');

    // Position: Relative to the bottom-right initial spot
    const translateX = useSharedValue(0);
    const translateY = useSharedValue(0);
    const lastOffsetX = useRef(0);
    const lastOffsetY = useRef(0);

    // Size and Pulse
    const width = useSharedValue(COLLAPSED_SIZE);
    const pulseScale = useSharedValue(1);
    const pulseOpacity = useSharedValue(0);

    const timerRef = useRef<NodeJS.Timeout | null>(null);

    const resetTimer = () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (!isExpanded) {
        timerRef.current = setInterval(() => {
          triggerPulse();
        }, PULSE_INTERVAL);
      }
    };

    const triggerPulse = () => {
      pulseScale.value = 1;
      pulseOpacity.value = 0.6;
      pulseScale.value = withTiming(2.2, { duration: 1500, easing: Easing.out(Easing.quad) });
      pulseOpacity.value = withTiming(0, { duration: 1500 });
    };

    const panResponder = useRef(
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: (_, gesture) => Math.abs(gesture.dx) > 2 || Math.abs(gesture.dy) > 2,
        onPanResponderGrant: () => {
          cancelAnimation(translateX);
          cancelAnimation(translateY);
          lastOffsetX.current = translateX.value;
          lastOffsetY.current = translateY.value;
        },
        onPanResponderMove: (_, gesture) => {
          translateX.value = lastOffsetX.current + gesture.dx;
          translateY.value = lastOffsetY.current + gesture.dy;
        },
        onPanResponderRelease: (_, gesture) => {
          const finalX = translateX.value;
          const finalY = translateY.value;

          // Snap logic: sticks to left or right
          const leftBoundary = -(SCREEN_WIDTH - COLLAPSED_SIZE - 40);
          const snapX = finalX > leftBoundary / 2 ? 0 : leftBoundary;

          translateX.value = withSpring(snapX, { damping: 20, stiffness: 150 });
          lastOffsetX.current = snapX;
          lastOffsetY.current = finalY;

          // Detected tap (only if movement was very small)
          if (Math.abs(gesture.dx) < 5 && Math.abs(gesture.dy) < 5) {
            handlePress();
          }
        },
        onPanResponderTerminationRequest: () => false, // Don't let others steal the touch
        onPanResponderTerminate: () => {
          // If terminated, snap back to last known good position
          translateX.value = withSpring(lastOffsetX.current);
          translateY.value = withSpring(lastOffsetY.current);
        },
        onShouldBlockNativeResponder: () => true, // Block native parents from taking over
      })
    ).current;

    useEffect(() => {
      resetTimer();
      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
      };
    }, [isExpanded]);

    const handlePress = () => {
      cancelAnimation(width);
      width.value = withSpring(ISLAND_WIDTH, { damping: 15, stiffness: 120 });
      setIslandState('island');
      resetTimer();

      setTimeout(() => {
        onExpandStart?.();
        onPress?.();
      }, 300);
    };

    useEffect(() => {
      if (!isExpanded) {
        cancelAnimation(width);
        width.value = withSpring(COLLAPSED_SIZE, { damping: 18, stiffness: 150 });
        setIslandState('collapsed');
      }
    }, [isExpanded]);

    const animatedStyle = useAnimatedStyle(() => {
      return {
        width: width.value,
        transform: [
          { translateX: translateX.value },
          { translateY: translateY.value },
        ],
      };
    });

    const pulseStyle = useAnimatedStyle(() => {
      return {
        transform: [
          { translateX: translateX.value },
          { translateY: translateY.value },
          { scale: pulseScale.value }
        ],
        opacity: pulseOpacity.value,
      };
    });

    if (isExpanded) return null;

    return (
      <View style={styles.outerContainer} pointerEvents="box-none">
        {/* Pulse Wave - Now using position transformation */}
        <Animated.View style={[styles.pulseCircle, pulseStyle]} pointerEvents="none" />

        {/* Island Container */}
        <Animated.View
          style={[styles.islandContainer, animatedStyle]}
          {...panResponder.panHandlers}
        >
          <BlurView intensity={95} tint="dark" style={styles.blurContainer}>
            <View style={styles.content}>
              <View style={styles.iconWrapper}>
                <MaterialIcons name="auto-awesome" size={24} color="#7C4DFF" />
              </View>

              {islandState === 'island' && (
                <Animated.View
                  entering={FadeIn.duration(300)}
                  style={styles.islandTextContainer}
                >
                  <Animated.Text style={styles.islandText}>AI Assistant</Animated.Text>
                </Animated.View>
              )}
            </View>
          </BlurView>
        </Animated.View>
      </View>
    );
  }
);

const styles = StyleSheet.create({
  outerContainer: {
    ...StyleSheet.absoluteFillObject,
    pointerEvents: 'box-none',
    zIndex: 999,
  },
  islandContainer: {
    position: 'absolute',
    bottom: 100,
    right: 20,
    height: COLLAPSED_SIZE,
    borderRadius: 28,
    overflow: 'hidden',
    backgroundColor: 'rgba(124, 77, 255, 0.25)',
    borderWidth: 2,
    borderColor: 'rgba(124, 77, 255, 0.5)',
    elevation: 12,
    shadowColor: '#7C4DFF',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.45,
    shadowRadius: 16,
    // Ensure expansion goes to the left
    alignSelf: 'flex-end',
  },
  blurContainer: {
    flex: 1,
  },
  content: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
  },
  iconWrapper: {
    width: 28,
    height: 28,
    justifyContent: 'center',
    alignItems: 'center',
  },
  islandTextContainer: {
    marginLeft: 12,
  },
  islandText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '800',
  },
  pulseCircle: {
    position: 'absolute',
    bottom: 100,
    right: 20,
    width: COLLAPSED_SIZE,
    height: COLLAPSED_SIZE,
    borderRadius: COLLAPSED_SIZE / 2,
    backgroundColor: '#7C4DFF',
    zIndex: -1,
  },
});

export default AIFloatingIsland;
