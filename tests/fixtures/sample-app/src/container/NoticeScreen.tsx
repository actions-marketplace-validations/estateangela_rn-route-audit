import { useTranslation } from 'react-i18next'

export function NoticeScreen() {
  const { t } = useTranslation()
  return (
    <View>
      <Header title={t('notice.title')} />
      <Text>{t('notice.body')}</Text>
    </View>
  )
}
