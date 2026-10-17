import { createStackNavigator } from '@react-navigation/stack'

import HomeScreen from '~/container/HomeScreen'
import DetailScreen from '~/container/DetailScreen.tsx'
import LoginScreen from '../container/LoginScreen'
import { NoticeScreen } from '~/container/NoticeScreen'
import { WalletRouterMap } from './WalletRouterMap'
import {
  DetailPath,
  DynamicPath,
  HomePath,
  LoginPath,
  NoticePath,
  WalletPath,
} from '~/router/path'

const Stack = createStackNavigator()

export default function RootNavigator({ flags }: { flags: { noticeEnabled: boolean } }) {
  return (
    <Stack.Navigator>
      <Stack.Screen name={LoginPath} component={LoginScreen} />

      <Stack.Screen
        name={HomePath}
        component={HomeScreen}
        options={({ route }) => ({ title: route.name, headerShown: true })}
      />

      <Stack.Screen name={DetailPath} component={DetailScreen} />

      <Stack.Screen name={WalletPath} component={WalletRouterMap.get(WalletPath)} />

      {flags.noticeEnabled && (
        <Stack.Screen name={NoticePath} component={NoticeScreen} />
      )}

      <Stack.Screen name={DynamicPath} component={makeScreen('dynamic')} />
    </Stack.Navigator>
  )
}
