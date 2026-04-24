import React from 'react';
import { View, Text, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import GlassBox from './GlassBox';

interface SummaryCardProps {
  totalBalance: number;
  periodBalance: number;
  month: number;
  year: number;
  onPrev: () => void;
  onNext: () => void;
  onDatePress?: () => void;
}

const SummaryCard: React.FC<SummaryCardProps> = ({
  totalBalance,
  periodBalance,
  month,
  year,
  onPrev,
  onNext,
  onDatePress,
}) => {
  const formatCurrency = (val: number) => {
    return val.toLocaleString('vi-VN') + ' đ';
  };

  return (
    <GlassBox className="h-[100px] justify-center" padding={16} intensity={40}>
      <View className="flex-row justify-between items-center">
        {/* Left Section: Total Balance */}
        <View className="flex-1">
          <View className="flex-row items-center gap-x-1.5 mb-1">
            <Ionicons name="wallet-outline" size={14} color="#00B0FF" />
            <Text className="text-[10px] font-medium text-gray-400">Tổng tích lũy</Text>
          </View>
          <Text 
            className="text-2xl font-bold text-white"
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.7}
          >
            {formatCurrency(totalBalance)}
          </Text>
        </View>

        {/* Vertical Divider */}
        <View className="w-[0.5px] h-10 bg-white/15 mx-4" />

        {/* Right Section: Time Nav + Monthly Balance */}
        <View className="flex-1 items-end">
          {/* Time Navigator */}
          <View className="flex-row items-center bg-white/5 rounded-md px-1 py-0.5 mb-1.5">
            <TouchableOpacity onPress={onPrev} className="p-0.5">
              <Ionicons name="chevron-back" size={14} color="#FFF" />
            </TouchableOpacity>
            <TouchableOpacity onPress={onDatePress}>
              <Text className="text-[11px] font-extrabold text-white mx-1 min-w-[44px] text-center">
                {`${String(month).padStart(2, '0')}/${year}`}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={onNext} className="p-0.5">
              <Ionicons name="chevron-forward" size={14} color="#FFF" />
            </TouchableOpacity>
          </View>

          {/* Monthly Amount */}
          <Text 
            className={`text-lg font-bold ${periodBalance >= 0 ? 'text-income' : 'text-expense'}`}
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.6}
          >
            {periodBalance >= 0 ? '+' : ''}{periodBalance.toLocaleString()}đ
          </Text>
        </View>
      </View>
    </GlassBox>
  );
};

export default SummaryCard;
