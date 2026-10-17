import { useTranslation } from 'react-i18next'

export default function DetailScreen() {
  const { t } = useTranslation()
  return <Header title={t('detail.title')} />
}
