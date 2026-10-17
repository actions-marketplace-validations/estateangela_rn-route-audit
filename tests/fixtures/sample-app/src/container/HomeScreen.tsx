import { useTranslation } from 'react-i18next'

export default function HomeScreen() {
  const { t } = useTranslation()
  return (
    <View>
      <Header title={t('home.title')} />
      <Text>{t('home.greeting')}</Text>
      <Button title={t('common.confirm')} />
    </View>
  )
}
