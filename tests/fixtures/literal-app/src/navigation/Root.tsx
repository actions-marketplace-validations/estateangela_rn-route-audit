import { createStackNavigator } from '@react-navigation/stack'

import Home from '../screens/Home'
import Settings from '../screens/Settings'

const Stack = createStackNavigator()
const DetailStack = createStackNavigator()

export function Root() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="Home" component={Home} />
      <Stack.Screen name="Settings" component={Settings} options={{ title: 'Settings' }} />
      <DetailStack.Screen name="Detail" component={() => null} />
    </Stack.Navigator>
  )
}
