import { createNativeStackNavigator } from '@react-navigation/native-stack'

import Feed from '../screens/Feed'
import Profile from '../screens/Profile'
import Settings from '../screens/Settings'

const Root = createNativeStackNavigator({
  screenOptions: { headerShown: true },
  screens: {
    Feed,
    Profile: { screen: Profile, options: { title: 'Profile' } },
    Settings: Settings,
  },
})

export default Root
