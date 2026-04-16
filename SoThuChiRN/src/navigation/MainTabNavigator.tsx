import React from 'react';
import { View, StyleSheet, TouchableOpacity, Platform } from 'react-native';
import { createBottomTabNavigator, BottomTabBarButtonProps } from '@react-navigation/bottom-tabs';
import { BlurView } from 'expo-blur';
import { Ionicons } from '@expo/vector-icons';
import { Colors, BorderRadius, FontSize, Spacing } from '../theme/colors';

// Screens
import DashboardScreen from '../screens/main/DashboardScreen';
import ExpenseScreen from '../screens/main/ExpenseScreen';
import CalendarScreen from '../screens/main/CalendarScreen';
import ReportScreen from '../screens/main/ReportScreen';
import SettingsScreen from '../screens/main/SettingsScreen';
import SearchScreen from '../screens/main/SearchScreen';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

export type MainTabParamList = {
  Dashboard: undefined;
  Calendar: undefined;
  Expense: undefined;
  Report: undefined;
  SettingsStack: undefined;
};

export type SettingsStackParamList = {
  SettingsBase: undefined;
  Search: undefined;
};

const Tab = createBottomTabNavigator<MainTabParamList>();
const SettingsStack = createNativeStackNavigator<SettingsStackParamList>();

function SettingsStackNavigator() {
  return (
    <SettingsStack.Navigator screenOptions={{ headerShown: false, animation: 'slide_from_right' }}>
      <SettingsStack.Screen name="SettingsBase" component={SettingsScreen} />
      <SettingsStack.Screen name="Search" component={SearchScreen} />
    </SettingsStack.Navigator>
  );
}

/**
 * Compact Custom FAB Button
 */
const CustomFabButton = ({ children, onPress }: BottomTabBarButtonProps) => (
  <TouchableOpacity
    style={styles.fabContainer}
    onPress={onPress}
    activeOpacity={0.8}
  >
    <View style={styles.fabGradient}>
      <Ionicons name="add" size={24} color={Colors.white} />
    </View>
  </TouchableOpacity>
);

export default function MainTabNavigator() {
  return (
    <Tab.Navigator
      initialRouteName="Dashboard"
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarShowLabel: true,
        tabBarActiveTintColor: Colors.accentBlue,
        tabBarInactiveTintColor: Colors.textTertiary,
        tabBarLabelStyle: styles.tabBarLabel,
        tabBarStyle: styles.tabBar,
        tabBarBackground: () => (
          <BlurView
            tint="dark"
            intensity={60}
            style={[StyleSheet.absoluteFill, { borderRadius: BorderRadius.xxl, overflow: 'hidden' }]}
          />
        ),
      })}
    >
      <Tab.Screen
        name="Dashboard"
        component={DashboardScreen}
        options={{
          tabBarLabel: 'Tổng quan',
          tabBarIcon: ({ color }) => <Ionicons name="grid-outline" size={18} color={color} />,
        }}
      />
      <Tab.Screen
        name="Calendar"
        component={CalendarScreen}
        options={{
          tabBarLabel: 'Lịch',
          tabBarIcon: ({ color }) => <Ionicons name="calendar-outline" size={18} color={color} />,
        }}
      />
      <Tab.Screen
        name="Expense"
        component={ExpenseScreen}
        options={{
          tabBarLabel: '',
          tabBarButton: (props) => <CustomFabButton {...props} />,
        }}
      />
      <Tab.Screen
        name="Report"
        component={ReportScreen}
        options={{
          tabBarLabel: 'Báo cáo',
          tabBarIcon: ({ color }) => <Ionicons name="pie-chart-outline" size={18} color={color} />,
        }}
      />
      <Tab.Screen
        name="SettingsStack"
        component={SettingsStackNavigator}
        options={{
          tabBarLabel: 'Khác',
          tabBarIcon: ({ color }) => <Ionicons name="options-outline" size={18} color={color} />,
        }}
      />
    </Tab.Navigator>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    position: 'absolute',
    bottom: 16, // Symmetrical margin
    left: 16,
    right: 16,
    height: 64, // Compact height
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
    borderRadius: BorderRadius.xxl,
    borderWidth: 0.4,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    elevation: 0,
    borderTopWidth: 0,
    paddingBottom: Platform.OS === 'ios' ? 18 : 8,
    paddingTop: 8,
  },
  tabBarLabel: {
    fontSize: FontSize.xs, // 10px
    fontWeight: '600',
    marginBottom: 0,
  },
  fabContainer: {
    top: -20,
    justifyContent: 'center',
    alignItems: 'center',
  },
  fabGradient: {
    width: 50, // Compact FAB
    height: 50,
    borderRadius: 25,
    backgroundColor: Colors.primaryGreen,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: Colors.primaryGreen,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    elevation: 6,
  },
});
