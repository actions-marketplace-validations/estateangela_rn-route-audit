import WalletScreen from '~/container/WalletScreen'
import { WalletPath } from '~/router/path'

export const WalletRouterMap = new Map<string, React.ComponentType>()
WalletRouterMap.set(WalletPath, WalletScreen)
