import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useAuth } from '../auth/AuthContext';
import { Loading } from '../components/ui';
import { InventoryEditScreen } from '../screens/InventoryEditScreen';
import { InventoryListScreen } from '../screens/InventoryListScreen';
import { LoginScreen } from '../screens/LoginScreen';
import { ProfileScreen } from '../screens/ProfileScreen';
import { RegisterScreen } from '../screens/RegisterScreen';
import { colors } from '../theme';

const Stack = createNativeStackNavigator();
const Tabs = createBottomTabNavigator();

function MainTabs() {
  return (
    <Tabs.Navigator screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.primary, tabBarLabelStyle: { fontSize: 14 }, tabBarStyle: { minHeight: 56 } }}>
      <Tabs.Screen name="Inventory" component={InventoryListScreen} />
      <Tabs.Screen name="Profile" component={ProfileScreen} />
    </Tabs.Navigator>
  );
}

export function RootNavigator() {
  const { status } = useAuth();
  if (status === 'loading') return <Loading />;
  return (
    <NavigationContainer>
      <Stack.Navigator>
        {status === 'signedIn' ? (
          <>
            <Stack.Screen name="Main" component={MainTabs} options={{ headerShown: false }} />
            <Stack.Screen name="InventoryEdit" component={InventoryEditScreen} options={({ route }: any) => ({ title: route.params?.item ? 'Inventory item' : 'Add inventory' })} />
          </>
        ) : (
          <>
            <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Register" component={RegisterScreen} options={{ title: 'Register' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
